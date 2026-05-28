"""MultiQuery查询扩展模块"""
import os
import json
import logging
import traceback
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import dashscope
    from dashscope import Generation
    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False

from config.retrieval_config import RetrievalConfig


class MultiQueryGenerator:
    """MultiQuery查询扩展生成器"""

    SYSTEM_PROMPT = """你是一个查询扩展专家。你的任务是根据用户问题生成多个语义相似的查询变体。

要求：
1. 生成 {num_variants} 个不同的查询变体
2. 每个变体保持原意，但用不同方式表达
3. 变体应该涵盖不同的搜索角度
4. 只输出查询列表，每行一个，不要其他解释

示例输入： 中芯国际2024年营收是多少？
示例输出：
中芯国际2024年营业收入
SMIC 2024年财报收入
中芯国际年度营收数据
中芯国际2024年财务业绩
公司2024年赚钱多少
"""

    def __init__(self, config: Optional[RetrievalConfig] = None):
        self.config = config or RetrievalConfig()
        self.num_variants = self.config.num_query_variants
        self.model = "qwen-turbo"
        logger.debug("MultiQueryGenerator.__init__: DASHSCOPE_AVAILABLE=%s, enable_multiquery=%s", DASHSCOPE_AVAILABLE, self.config.enable_multiquery)
        if DASHSCOPE_AVAILABLE:
            self.api_key = self._get_api_key()

    def _get_api_key(self) -> str:
        """获取API密钥"""
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
        if not api_key or api_key == "your_dashscope_api_key_here":
            raise ValueError("请在.env中设置DASHSCOPE_API_KEY")
        return api_key

    def generate_variants(self, query: str) -> List[str]:
        """生成查询变体"""
        logger.debug("MultiQueryGenerator.generate_variants: enable_multiquery=%s, DASHSCOPE_AVAILABLE=%s", self.config.enable_multiquery, DASHSCOPE_AVAILABLE)
        if not self.config.enable_multiquery:
            logger.debug("MultiQuery已禁用，返回原始查询")
            return [query]

        if not DASHSCOPE_AVAILABLE:
            logger.debug("DashScope不可用，返回原始查询")
            return [query]

        try:
            logger.debug("MultiQuery调用LLM: model=%s, query='%s'", self.model, query)
            response = Generation.call(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT.format(num_variants=self.num_variants)},
                    {"role": "user", "content": query}
                ],
                api_key=self.api_key,
                result_format="message"
            )

            if response.status_code == 200:
                content = response.output.choices[0].message.content.strip()
                logger.debug("MultiQuery LLM响应: %s", content[:200])
                variants = [v.strip() for v in content.split("\n") if v.strip()]
                if getattr(self.config, 'include_original', True) and query not in variants:
                    variants.insert(0, query)
                logger.debug("MultiQuery生成%d个变体: %s", len(variants), variants)
                return variants[:self.num_variants]
            else:
                logger.error("MultiQuery API调用失败: status=%s, message=%s", response.status_code, response.message)
                return [query]
        except Exception as e:
            if "ConnectionError" in type(e).__name__ or "NameResolutionError" in str(e) or "MaxRetryError" in str(e):
                logger.warning("MultiQuery API不可用，跳过: %s", type(e).__name__)
            else:
                logger.error("MultiQuery生成异常: %s", e)
                traceback.print_exc()
            return [query]

    def expand_and_search(self, query: str, search_func) -> Dict[str, Any]:
        """
        扩展查询并执行搜索

        Args:
            query: 原始查询
            search_func: 搜索函数，签名为 search(query, top_k) -> List[Dict]

        Returns:
            {
                "original_query": str,
                "query_variants": List[str],
                "merged_results": List[Dict],  # 合并后的结果
                "stats": {...}
            }
        """
        # 生成变体
        variants = self.generate_variants(query)

        # 执行搜索
        all_results = []
        for variant in variants:
            try:
                results = search_func(variant, self.config.top_k_retrieval)
                all_results.append((variant, results))
            except Exception as e:
                logger.error("搜索失败 '%s': %s", variant, e)

        # 合并结果
        merged = self._merge_results(all_results)

        return {
            "original_query": query,
            "query_variants": variants,
            "merged_results": merged["results"],
            "stats": {
                "total_candidates": merged["total_candidates"],
                "unique_results": merged["unique_count"],
                "variant_count": len(variants)
            }
        }

    def _merge_results(self, results: List[Tuple[str, List[Dict]]]) -> Dict[str, Any]:
        """合并多个搜索结果"""
        score_map: Dict[str, Dict[str, Any]] = {}
        variant_counts: Dict[str, int] = {}

        for variant, variant_results in results:
            for r in variant_results:
                chunk_id = r.get("chunk_id", "")
                if not chunk_id:
                    continue

                if chunk_id not in score_map:
                    score_map[chunk_id] = r.copy()
                    score_map[chunk_id]["variants"] = []
                    score_map[chunk_id]["variant_count"] = 0
                else:
                    # 更新最高分
                    if r.get("score", 0) > score_map[chunk_id].get("score", 0):
                        score_map[chunk_id]["score"] = r["score"]

                score_map[chunk_id]["variants"].append(variant)
                score_map[chunk_id]["variant_count"] += 1
                variant_counts[chunk_id] = variant_counts.get(chunk_id, 0) + 1

        # 按分数排序
        sorted_results = sorted(score_map.values(), key=lambda x: x.get("score", 0), reverse=True)

        return {
            "results": sorted_results,
            "total_candidates": sum(len(v) for _, v in results),
            "unique_count": len(score_map)
        }


class QueryRewriter:
    """Query改写模块 - 将口语化问题改写为检索友好形式"""

    SYSTEM_PROMPT = """你是一个查询改写专家。你的任务是将用户的口语化问题改写为检索友好的查询表达式。

改写原则：
1. 展开缩写和简称（如"华为"->"华为技术有限公司"）
2. 消除指代（如"它"->具体公司名"中芯国际"）
3. 使用规范术语（如"赚钱"->"营业收入"）
4. 补充必要的上下文

只输出改写后的查询语句，不要解释。

示例输入：我想知道公司去年赚了多少钱
示例输出：中芯国际2024年营业收入

示例输入：它的研发投入是多少
示例输出：中芯国际2024年研发投入
"""

    def __init__(self, config: Optional[RetrievalConfig] = None):
        self.config = config or RetrievalConfig()
        self.model = "qwen-turbo"

    def rewrite(self, query: str, history_context: Optional[str] = None) -> Dict[str, Any]:
        """
        改写查询

        Args:
            query: 原始查询
            history_context: 可选的对话历史上下文

        Returns:
            {
                "original": str,
                "rewritten": str,
                "confidence": float,
                "used_history": bool
            }
        """
        logger.debug("QueryRewriter.rewrite: enable_query_rewrite=%s, DASHSCOPE_AVAILABLE=%s", self.config.enable_query_rewrite, DASHSCOPE_AVAILABLE)
        if not self.config.enable_query_rewrite:
            logger.debug("Query改写已禁用，返回原始查询")
            return {
                "original": query,
                "rewritten": query,
                "confidence": 1.0,
                "used_history": False
            }

        if not DASHSCOPE_AVAILABLE:
            logger.debug("DashScope不可用，返回原始查询")
            return {
                "original": query,
                "rewritten": query,
                "confidence": 1.0,
                "used_history": False
            }

        api_key = self._get_api_key()

        user_content = query
        if history_context:
            user_content = f"对话历史：{history_context}\n\n当前问题：{query}"

        try:
            logger.debug("Query改写调用LLM: model=%s, query='%s'", self.model, query)
            response = Generation.call(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                api_key=api_key,
                result_format="message"
            )

            if response.status_code == 200:
                rewritten = response.output.choices[0].message.content.strip()
                logger.debug("Query改写成功: '%s' -> '%s'", query, rewritten)
                return {
                    "original": query,
                    "rewritten": rewritten,
                    "confidence": 0.9,
                    "used_history": bool(history_context)
                }
            else:
                logger.error("Query改写 API调用失败: status=%s, message=%s", response.status_code, response.message)
                return {
                    "original": query,
                    "rewritten": query,
                    "confidence": 0.0,
                    "used_history": False
                }
        except Exception as e:
            if "ConnectionError" in type(e).__name__ or "NameResolutionError" in str(e) or "MaxRetryError" in str(e):
                logger.warning("Query改写 API不可用，跳过: %s", type(e).__name__)
            else:
                logger.error("Query改写异常: %s", e)
                traceback.print_exc()
            return {
                "original": query,
                "rewritten": query,
                "confidence": 0.0,
                "used_history": False
            }

    def _get_api_key(self) -> str:
        """获取API密钥"""
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
        if not api_key or api_key == "your_dashscope_api_key_here":
            raise ValueError("请在.env中设置DASHSCOPE_API_KEY")
        return api_key