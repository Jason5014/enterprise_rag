"""重排模块 - LLM重排（支持 Listwise / Pointwise）"""
import os
import json
import re
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import dashscope
    from dashscope import Generation
    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False

from config.retrieval_config import RetrievalConfig
from src.utils import get_api_key


class LLMReranker:
    """LLM重排器"""

    SYSTEM_PROMPT = """你是一个相关性评估专家。给定一个查询和一段文本，评估文本与查询的相关程度。

评分标准：
- 9-10分：文本完全回答了查询问题，包含查询所需的关键信息
- 7-8分：文本与查询高度相关，提供了大部分相关信息
- 4-6分：文本与查询中度相关，但缺少关键信息或有一定偏差
- 1-3分：文本与查询相关性低，只有少量相关信息
- 0分：文本与查询完全不相关

输出格式：
分数: X
理由: 简要说明

注意：只输出分数和理由，不要其他内容。"""

    USER_PROMPT_TEMPLATE = """查询：{query}

候选文本：
{context}

评估："""

    LISTWISE_SYSTEM_PROMPT = """你是检索结果重排专家。给定查询和多个候选文本块，对每个文本块与查询的相关性打分（0-10）。

输出严格的JSON格式，不要有任何其他内容：
{"rankings": [{"index": 0, "score": 8}, {"index": 1, "score": 3}, ...]}

说明：
- index 对应候选文本的序号（从0开始）
- score 范围 0-10，10分最相关
- 必须为每个候选给出分数"""

    def __init__(self, config: Optional[RetrievalConfig] = None):
        self.config = config or RetrievalConfig()
        self.rerank_top_k = self.config.rerank_top_k
        self.llm_weight = self.config.llm_weight
        self.rerank_mode = getattr(self.config, 'rerank_mode', 'listwise')
        self.model = "qwen-turbo"
        self.batch_size = 2  # pointwise 模式每批数量
        self._api_unavailable = False  # API不可用标记

    def rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        对候选结果重排

        Args:
            query: 查询问题
            candidates: 候选结果列表，每项包含 chunk_id, text, parent_text 等
            top_k: 返回数量，默认使用配置中的 rerank_top_k

        Returns:
            重排后的结果列表
        """
        if not candidates:
            return []

        effective_top_k = top_k if top_k is not None else self.rerank_top_k

        if self._api_unavailable:
            for i, r in enumerate(candidates[:effective_top_k]):
                r["combined_score"] = r.get("score", 0)
                r["rank"] = i + 1
            return candidates[:effective_top_k]

        # 根据模式选择重排方式
        if self.rerank_mode == "listwise":
            all_scores = self._rerank_listwise(query, candidates)
        else:
            # pointwise：按批次逐条处理
            all_scores = []
            for i in range(0, len(candidates), self.batch_size):
                batch = candidates[i:i + self.batch_size]
                batch_scores = self._rerank_batch(query, batch)
                all_scores.extend(batch_scores)

        # 合并分数
        for i, candidate in enumerate(candidates):
            llm_score = all_scores[i] if i < len(all_scores) else 0
            vector_score = candidate.get("score", 0)

            # 综合分数 = llm_weight * llm_score + (1-llm_weight) * vector_score
            combined_score = self.llm_weight * (llm_score / 10.0) + (1 - self.llm_weight) * vector_score

            candidate["llm_score"] = llm_score
            candidate["combined_score"] = combined_score

        # 按综合分数排序
        sorted_results = sorted(candidates, key=lambda x: x.get("combined_score", 0), reverse=True)

        # 返回effective_top_k
        for i, r in enumerate(sorted_results[:effective_top_k]):
            r["rank"] = i + 1

        return sorted_results[:effective_top_k]

    def _rerank_listwise(self, query: str, candidates: List[Dict[str, Any]]) -> List[float]:
        """Listwise 重排：一次 API 调用对所有候选打分"""
        if not candidates:
            return []
        if self._api_unavailable:
            return [0.0] * len(candidates)

        blocks = "\n\n---\n\n".join(
            f"[{i}]\n{c.get('parent_text', c.get('text', ''))[:800]}"
            for i, c in enumerate(candidates)
        )
        user_prompt = f"查询：{query}\n\n候选文本块：\n{blocks}"

        try:
            api_key = get_api_key()
            response = Generation.call(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.LISTWISE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                api_key=api_key,
                temperature=0
            )
            if response.status_code != 200:
                logger.error("Listwise重排 API失败: %s", response.message)
                return [0.0] * len(candidates)

            content = response.output.get("text", "").strip()
            # 提取 JSON
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if not match:
                logger.warning("Listwise重排无法解析JSON: %s", content[:200])
                return [0.0] * len(candidates)

            data = json.loads(match.group())
            rankings = data.get("rankings", [])
            scores = [0.0] * len(candidates)
            for item in rankings:
                idx = item.get("index", -1)
                score = item.get("score", 0)
                if 0 <= idx < len(scores):
                    scores[idx] = float(score)
            return scores

        except Exception as e:
            if "ConnectionError" in type(e).__name__ or "NameResolutionError" in str(e):
                logger.warning("Listwise重排 API不可用，跳过: %s", type(e).__name__)
                self._api_unavailable = True
            else:
                logger.error("Listwise重排失败: %s", e)
            return [0.0] * len(candidates)

    def _rerank_batch(self, query: str, batch: List[Dict[str, Any]]) -> List[float]:
        """对一批候选进行重排评分"""
        scores = []

        for candidate in batch:
            if self._api_unavailable:
                scores.append(0)
                continue
            try:
                score = self._get_llm_score(query, candidate)
                scores.append(score)
            except Exception as e:
                if "ConnectionError" in type(e).__name__ or "NameResolutionError" in str(e) or "MaxRetryError" in str(e):
                    logger.warning("LLM重排API不可用，跳过后续重排: %s", type(e).__name__)
                    self._api_unavailable = True
                    scores.append(0)
                else:
                    logger.error("LLM评分失败: %s", e)
                    scores.append(0)

        return scores

    def _get_llm_score(self, query: str, candidate: Dict[str, Any]) -> float:
        """使用LLM获取相关性分数"""
        # 使用父Chunk文本（如果启用PDR）或者子Chunk文本
        context = candidate.get("parent_text", candidate.get("text", ""))

        if not context:
            context = candidate.get("text", "")

        user_prompt = self.USER_PROMPT_TEMPLATE.format(
            query=query,
            context=context[:2000]  # 限制长度
        )

        try:
            api_key = get_api_key()
            response = Generation.call(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                api_key=api_key
            )

            if response.status_code == 200:
                content = response.output.get("text", "").strip()
                # 解析分数
                score = self._parse_score(content)
                return score
            else:
                logger.error("LLM重排 API调用失败: status=%s, message=%s", response.status_code, response.message)
                return 0
        except Exception as e:
            raise  # 向上抛出，由 _rerank_batch 统一处理

    def _parse_score(self, content: str) -> float:
        """从LLM输出中解析分数"""
        try:
            # 尝试提取 "分数: X" 格式
            for line in content.split("\n"):
                if "分数" in line or "score" in line.lower():
                    # 提取数字
                    import re
                    numbers = re.findall(r'\d+\.?\d*', line)
                    if numbers:
                        return float(numbers[0])
            return 0
        except Exception as e:
            logger.error("解析LLM分数失败: %s", e)
            return 0



class JinaReranker:
    """Jina AI Reranker - LLM重排的替代方案"""

    def __init__(self, api_key: Optional[str] = None, model: str = "jina-reranker-v1-base-en"):
        from dotenv import load_dotenv
        load_dotenv()
        self.api_key = api_key or os.getenv("JINA_API_KEY", "")
        self.model = model
        self.top_n = 10

    def rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: Optional[int] = None, top_n: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        使用Jina Reranker重排

        Args:
            query: 查询问题
            candidates: 候选结果列表
            top_k: 返回数量（兼容top_n参数名）
            top_n: 返回数量（别名）

        Returns:
            重排后的结果列表
        """
        effective_top_k = top_k if top_k is not None else (top_n if top_n is not None else self.top_n)
        if not candidates:
            return []

        if not self.api_key:
            # 没有API Key，使用简单分数排序
            return sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)[:effective_top_k]

        try:
            import requests

            # 准备数据
            texts = [c.get("text", c.get("parent_text", ""))[:2000] for c in candidates]

            response = requests.post(
                "https://api.jina.ai/v1/rerank",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "query": query,
                    "documents": texts,
                    "top_n": effective_top_k,
                    "return_documents": False
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                results = result.get("results", [])

                # 更新候选结果
                for i, r in enumerate(results):
                    idx = r["index"]
                    if idx < len(candidates):
                        candidates[idx]["jina_score"] = r["relevance_score"]
                        candidates[idx]["combined_score"] = r["relevance_score"]

                # 按Jina分数排序
                sorted_results = sorted(candidates, key=lambda x: x.get("jina_score", 0), reverse=True)

                for i, r in enumerate(sorted_results):
                    r["rank"] = i + 1

                return sorted_results[:effective_top_k]
            else:
                logger.error("Jina Reranker API失败: %s", response.status_code)
                return candidates[:effective_top_k]

        except Exception as e:
            logger.error("Jina Reranker调用失败: %s", e)
            return candidates[:effective_top_k]