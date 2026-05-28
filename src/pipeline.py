"""RAG流程管道 - 串联各模块实现完整问答流程"""
from typing import Dict, Any, Optional, List
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)

from config.settings import ConfigBundle
from config.retrieval_config import RetrievalConfig
from config.answer_config import AnswerConfig

from src.retriever import HybridRetriever
from src.reranker import LLMReranker, JinaReranker
from src.multi_query import MultiQueryGenerator, QueryRewriter
from src.query_router import QueryRouter, QueryType
from src.answer_generator import AnswerGenerator, ConversationHistory
from src.retrieval_logger import RetrievalLogger


class RAGPipeline:
    """RAG主流程管道 - 串联MultiQuery、检索、重排、答案生成"""

    def __init__(self, config: ConfigBundle):
        """初始化管道"""
        self.config = config
        self.retrieval_config = config.retrieval or RetrievalConfig()
        self.answer_config = config.answer or AnswerConfig()

        # 初始化各模块
        self._init_retriever()
        self._init_reranker()
        self._init_query_processor()
        self._init_answer_generator()
        self._init_logger()

    def _init_retriever(self):
        """初始化检索器"""
        self.retriever = HybridRetriever(self.retrieval_config)
        index_dir = getattr(self.retrieval_config, 'index_dir', "data/chunked")
        try:
            self.retriever.load_index(index_dir)
        except Exception as e:
            logger.error("索引加载失败: %s", e)

    def _init_reranker(self):
        """初始化重排器"""
        if self.retrieval_config.use_jina_reranker:
            self.reranker = JinaReranker()
        else:
            self.reranker = LLMReranker(self.retrieval_config)

    def _init_query_processor(self):
        """初始化查询处理器"""
        self.multi_query = MultiQueryGenerator(self.retrieval_config)
        self.query_rewriter = QueryRewriter(self.retrieval_config)

    def _init_answer_generator(self):
        """初始化答案生成器"""
        self.answer_generator = AnswerGenerator(
            self.answer_config,
            self.retrieval_config
        )
        self.conversation_history = ConversationHistory(
            max_turns=self.retrieval_config.max_history_turns,
            max_tokens=4000
        )

    def _init_logger(self):
        """初始化日志记录器"""
        self.logger = RetrievalLogger(log_dir="data/logs", log_level="INFO")
        self._last_retrieval_log = None

    def answer_single_question(
        self,
        question: str,
        return_retrieval_details: bool = False
    ) -> Dict[str, Any]:
        """
        回答单个问题

        Args:
            question: 用户问题
            return_retrieval_details: 是否返回检索详情

        Returns:
            {
                "step_by_step_analysis": str,   # 详细推理过程
                "reasoning_summary": str,       # 50字以内摘要
                "relevant_pages": List[int],    # 引用页码
                "final_answer": str,            # 具体答案
                "used_parent_chunks": List[str], # 使用的父Chunk ID
                "retrieval_details": dict        # 可选的检索详情
            }
        """
        log_id = self.logger.start_retrieval(question)

        try:
            import time as _time

            # Step 1: Query改写（如启用）
            logger.debug("pipeline配置: enable_query_rewrite=%s, enable_multiquery=%s", self.retrieval_config.enable_query_rewrite, self.retrieval_config.enable_multiquery)
            if self.retrieval_config.enable_query_rewrite:
                logger.debug("开始Query改写...")
                _t0 = _time.time()
                self.logger.start_stage("query_rewrite", {"original": question})
                rewrite_result = self.query_rewriter.rewrite(
                    question,
                    history_context=self.conversation_history.get_context()
                )
                rewritten_query = rewrite_result["rewritten"]
                _t1 = _time.time()
                logger.debug("Query改写完成: 耗时=%.1fms, rewritten='%s', confidence=%s", (_t1-_t0)*1000, rewritten_query, rewrite_result['confidence'])
                self.logger.end_stage({
                    "rewritten": rewritten_query,
                    "confidence": rewrite_result["confidence"],
                    "query_type": "rewritten" if rewrite_result["confidence"] > 0.5 else "original"
                })
            else:
                logger.debug("Query改写已禁用，跳过")
                rewritten_query = question

            # Step 2: MultiQuery扩展（如启用）
            if self.retrieval_config.enable_multiquery:
                logger.debug("开始MultiQuery扩展...")
                _t0 = _time.time()
                self.logger.start_stage("multiquery")
                query_variants = self.multi_query.generate_variants(question)
                _t1 = _time.time()
                logger.debug("MultiQuery完成: 耗时=%.1fms, variants=%s", (_t1-_t0)*1000, query_variants)
                self.logger.end_stage({
                    "variants": query_variants
                })
            else:
                logger.debug("MultiQuery已禁用，跳过")
                query_variants = [rewritten_query]

            # Step 3: 混合检索
            self.logger.start_stage("retrieval")
            all_results = []
            for variant in query_variants:
                try:
                    results = self.retriever.search(variant, top_k=self.retrieval_config.top_k_retrieval)
                    all_results.extend(results)
                except Exception as e:
                    logger.error("检索失败 '%s': %s", variant, e)

            # 合并去重
            merged_results = self._merge_search_results(all_results)
            # 保存检索结果摘要（前5条）
            retrieval_summary = []
            for r in merged_results[:5]:
                retrieval_summary.append({
                    "chunk_id": r.get("chunk_id", ""),
                    "text": (r.get("parent_text") or r.get("text", ""))[:150],
                    "score": round(r.get("score", 0), 4),
                    "source": r.get("source", "unknown")
                })
            self.logger.end_stage({
                "result_count": len(merged_results),
                "bm25_count": sum(1 for r in merged_results if r.get("source") == "bm25"),
                "vector_count": sum(1 for r in merged_results if r.get("source") == "vector"),
                "top_results": retrieval_summary
            })

            # Step 4: LLM重排（如启用）
            if self.retrieval_config.enable_rerank and merged_results:
                self.logger.start_stage("rerank")
                import copy
                reranked_results = self.reranker.rerank(
                    question,
                    copy.deepcopy(merged_results),
                    top_k=self.retrieval_config.rerank_top_k
                )
                # 保存重排结果摘要
                rerank_summary = []
                for r in reranked_results[:5]:
                    rerank_summary.append({
                        "chunk_id": r.get("chunk_id", ""),
                        "text": (r.get("parent_text") or r.get("text", ""))[:150],
                        "score": round(r.get("combined_score", r.get("score", 0)), 4),
                        "source": r.get("source", "unknown")
                    })
                self.logger.end_stage({
                    "result_count": len(reranked_results),
                    "top_score": reranked_results[0].get("combined_score") if reranked_results else 0,
                    "top_results": rerank_summary
                })
            else:
                reranked_results = merged_results[:self.retrieval_config.rerank_top_k]

            # Step 5: 答案生成
            self.logger.start_stage("generate")

            # 获取对话历史上下文
            history = None
            if self.retrieval_config.enable_history:
                history = [{"role": "user", "content": h} for h in
                          [self.conversation_history.history[i]["content"]
                           for i in range(0, len(self.conversation_history.history), 2)]]

            answer = self.answer_generator.generate(
                query=question,
                context=reranked_results,
                history=history
            )

            self.logger.end_stage({
                "answer_length": len(answer.get("final_answer", "")),
                "pages_cited": len(answer.get("relevant_pages", []))
            })

            # 完成日志
            self.logger.finish_retrieval(reranked_results)
            self._last_retrieval_log = self.logger.get_summary()
            self.logger.save()

            # 更新对话历史
            if self.retrieval_config.enable_history:
                self.conversation_history.add("user", question)
                self.conversation_history.add("assistant", answer.get("final_answer", ""))

            # 构建返回结果
            result = {
                "step_by_step_analysis": answer.get("step_by_step_analysis", ""),
                "reasoning_summary": answer.get("reasoning_summary", ""),
                "relevant_pages": answer.get("relevant_pages", []),
                "final_answer": answer.get("final_answer", "N/A"),
                "used_parent_chunks": answer.get("used_parent_chunks", [])
            }

            if return_retrieval_details:
                result["retrieval_details"] = {
                    "rewritten_query": rewritten_query,
                    "query_variants": query_variants,
                    "retrieval_results": reranked_results,
                    "latency_ms": self.logger._current_log.latency_ms if self.logger._current_log else {}
                }

            return result

        except Exception as e:
            self.logger.error(f"问答处理失败: {e}")
            self.logger.save()
            return {
                "step_by_step_analysis": f"处理失败: {str(e)}",
                "reasoning_summary": "处理失败",
                "relevant_pages": [],
                "final_answer": "N/A",
                "used_parent_chunks": []
            }

    def _merge_search_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """合并多个搜索结果，按chunk_id去重并保留最高分"""
        seen = {}
        for r in results:
            chunk_id = r.get("chunk_id")
            if chunk_id and chunk_id not in seen:
                seen[chunk_id] = r
            elif chunk_id and r.get("score", 0) > seen[chunk_id].get("score", 0):
                seen[chunk_id] = r

        # 按分数排序
        sorted_results = sorted(
            seen.values(),
            key=lambda x: x.get("score", 0),
            reverse=True
        )
        return sorted_results

    def answer_batch(
        self,
        questions: List[str],
        show_progress: bool = True
    ) -> List[Dict[str, Any]]:
        """
        批量回答问题

        Args:
            questions: 问题列表
            show_progress: 是否显示进度

        Returns:
            结果列表
        """
        results = []
        total = len(questions)

        for i, q in enumerate(questions):
            if show_progress:
                logger.info("[%d/%d] 处理: %s...", i+1, total, q[:50])

            result = self.answer_single_question(q)
            results.append(result)

        return results

    def get_last_retrieval_log(self) -> Optional[Dict[str, Any]]:
        """获取上次检索的日志摘要"""
        return self._last_retrieval_log

    def retrieve(self, question: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        纯检索（不生成答案），用于评估测试完整流程
        包含：查询改写 → MultiQuery扩展 → 混合检索 → 重排

        Args:
            question: 用户问题
            top_k: 返回数量（默认使用配置中的top_k_retrieval）

        Returns:
            重排后的检索结果列表
        """
        k = top_k or self.retrieval_config.top_k_retrieval

        # Step 1: Query改写（如启用）
        rewrite_result = self.query_rewriter.rewrite(question)
        rewritten_query = rewrite_result["rewritten"]

        # Step 2: MultiQuery扩展（如启用）
        if self.retrieval_config.enable_multiquery:
            query_variants = self.multi_query.generate_variants(question)
        else:
            query_variants = [rewritten_query]

        # Step 3: 混合检索
        all_results = []
        for variant in query_variants:
            try:
                results = self.retriever.search(variant, top_k=k)
                all_results.extend(results)
            except Exception as e:
                logger.error("检索失败 '%s': %s", variant, e)

        # 合并去重
        merged_results = self._merge_search_results(all_results)

        # Step 4: 重排（如启用）
        if self.retrieval_config.enable_rerank and merged_results:
            reranked_results = self.reranker.rerank(
                question,
                merged_results,
                top_k=self.retrieval_config.rerank_top_k
            )
            return reranked_results
        else:
            return merged_results[:k]

    def get_stats(self) -> Dict[str, Any]:
        """获取管道统计信息"""
        stats = {
            "retrieval": self.retriever.get_retrieval_info() if hasattr(self.retriever, 'get_retrieval_info') else {},
            "config": {
                "enable_multiquery": self.retrieval_config.enable_multiquery,
                "enable_rerank": self.retrieval_config.enable_rerank,
                "enable_history": self.retrieval_config.enable_history,
                "top_k_retrieval": self.retrieval_config.top_k_retrieval,
                "rerank_top_k": self.retrieval_config.rerank_top_k
            }
        }
        return stats

    def reset_history(self):
        """重置对话历史"""
        self.conversation_history.clear()