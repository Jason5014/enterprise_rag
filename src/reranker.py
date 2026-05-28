"""重排模块 - LLM重排"""
import os
import json
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

    def __init__(self, config: Optional[RetrievalConfig] = None):
        self.config = config or RetrievalConfig()
        self.rerank_top_k = self.config.rerank_top_k
        self.llm_weight = self.config.llm_weight
        self.model = "qwen-turbo"
        self.batch_size = 2  # 每次重排的候选数量
        self.max_workers = 1  # 串行避免QPS超限
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
            # API已标记不可用，直接返回原结果
            for i, r in enumerate(candidates[:effective_top_k]):
                r["combined_score"] = r.get("score", 0)
                r["rank"] = i + 1
            return candidates[:effective_top_k]

        # 按批次处理
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
            api_key = self._get_api_key()
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

    def _get_api_key(self) -> str:
        """获取API密钥"""
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
        if not api_key or api_key == "your_dashscope_api_key_here":
            raise ValueError("请在.env中设置DASHSCOPE_API_KEY")
        return api_key


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