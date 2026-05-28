"""检索与重排模块测试"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


class TestMultiQueryGenerator:
    """MultiQueryGenerator测试"""

    def test_init(self):
        """测试初始化"""
        from src.multi_query import MultiQueryGenerator
        from config.retrieval_config import RetrievalConfig

        config = RetrievalConfig(enable_multiquery=True, num_query_variants=3)
        mq = MultiQueryGenerator(config=config)
        assert mq.num_variants == 3

    def test_generate_variants_disabled(self):
        """测试禁用时返回原始查询"""
        from src.multi_query import MultiQueryGenerator
        from config.retrieval_config import RetrievalConfig

        config = RetrievalConfig(enable_multiquery=False)
        mq = MultiQueryGenerator(config=config)
        result = mq.generate_variants("测试查询")
        assert result == ["测试查询"]

    def test_merge_results(self):
        """测试结果合并"""
        from src.multi_query import MultiQueryGenerator

        mq = MultiQueryGenerator()

        results = [
            ("查询1", [
                {"chunk_id": "c1", "score": 0.9, "text": "text1"},
                {"chunk_id": "c2", "score": 0.8, "text": "text2"}
            ]),
            ("查询2", [
                {"chunk_id": "c2", "score": 0.85, "text": "text2"},
                {"chunk_id": "c3", "score": 0.7, "text": "text3"}
            ])
        ]

        merged = mq._merge_results(results)

        assert merged["total_candidates"] == 4
        assert merged["unique_count"] == 3
        assert "c1" in [r["chunk_id"] for r in merged["results"]]
        assert "c2" in [r["chunk_id"] for r in merged["results"]]
        assert "c3" in [r["chunk_id"] for r in merged["results"]]


class TestQueryRewriter:
    """QueryRewriter测试"""

    def test_init(self):
        """测试初始化"""
        from src.multi_query import QueryRewriter

        qw = QueryRewriter()
        assert qw.model == "qwen-turbo"

    def test_rewrite_disabled(self):
        """测试禁用时返回原始"""
        from src.multi_query import QueryRewriter
        from config.retrieval_config import RetrievalConfig

        config = RetrievalConfig(enable_query_rewrite=False)
        qw = QueryRewriter(config=config)

        result = qw.rewrite("原始查询")
        assert result["original"] == "原始查询"
        assert result["rewritten"] == "原始查询"
        assert result["confidence"] == 1.0


class TestHybridRetriever:
    """HybridRetriever测试"""

    def test_init(self):
        """测试初始化"""
        from src.retriever import HybridRetriever
        from config.retrieval_config import RetrievalConfig

        config = RetrievalConfig(bm25_weight=0.3, vector_weight=0.7)
        retriever = HybridRetriever(config=config)
        assert retriever.bm25_weight == 0.3
        assert retriever.vector_weight == 0.7

    def test_fuse_results_empty(self):
        """测试空结果融合"""
        from src.retriever import HybridRetriever

        retriever = HybridRetriever()
        fused = retriever._fuse_results([], [], 5)
        assert fused == []

    def test_fuse_results_bm25_only(self):
        """测试仅有BM25结果"""
        from src.retriever import HybridRetriever

        retriever = HybridRetriever()
        bm25_results = [
            {"chunk_id": "c1", "score": 10.0, "text": "text1"},
            {"chunk_id": "c2", "score": 8.0, "text": "text2"}
        ]
        fused = retriever._fuse_results(bm25_results, [], 5)

        assert len(fused) == 2
        # 检查归一化后的分数
        assert fused[0]["bm25_score"] == 1.0  # 最高分为1.0
        assert fused[1]["bm25_score"] == 0.8  # 8/10=0.8

    def test_fuse_results_both(self):
        """测试BM25和Vector混合"""
        from src.retriever import HybridRetriever

        retriever = HybridRetriever()

        bm25_results = [
            {"chunk_id": "c1", "score": 10.0, "text": "text1"},
            {"chunk_id": "c2", "score": 8.0, "text": "text2"}
        ]
        vector_results = [
            {"chunk_id": "c1", "score": 0.95, "text": "text1"},
            {"chunk_id": "c3", "score": 0.9, "text": "text3"}
        ]

        fused = retriever._fuse_results(bm25_results, vector_results, 5)

        assert len(fused) == 3
        # c1同时出现在两个结果中，应该分数更高
        c1_result = next(r for r in fused if r["chunk_id"] == "c1")
        assert c1_result["bm25_score"] == 1.0
        assert c1_result["vector_score"] == 1.0  # 归一化后

    def test_attach_parent_chunks(self):
        """测试附加父Chunk"""
        from src.retriever import HybridRetriever

        retriever = HybridRetriever()
        retriever._parent_chunks = {
            "p1": {"chunk_id": "p1", "text": "父文本1"},
            "p2": {"chunk_id": "p2", "text": "父文本2"}
        }

        results = [
            {"chunk_id": "c1", "parent_id": "p1", "text": "子文本1"},
            {"chunk_id": "c2", "parent_id": "p2", "text": "子文本2"}
        ]

        attached = retriever._attach_parent_chunks(results)

        assert attached[0]["parent_text"] == "父文本1"
        assert attached[0]["parent_chunk"]["chunk_id"] == "p1"
        assert attached[1]["parent_text"] == "父文本2"

    def test_get_retrieval_info(self):
        """测试获取检索器信息"""
        from src.retriever import HybridRetriever

        retriever = HybridRetriever()
        info = retriever.get_retrieval_info()

        assert "bm25_weight" in info
        assert "vector_weight" in info
        assert "enable_parent_retrieval" in info


class TestLLMReranker:
    """LLMReranker测试"""

    def test_init(self):
        """测试初始化"""
        from src.reranker import LLMReranker
        from config.retrieval_config import RetrievalConfig

        config = RetrievalConfig(rerank_top_k=5, llm_weight=0.7)
        reranker = LLMReranker(config=config)
        assert reranker.rerank_top_k == 5
        assert reranker.llm_weight == 0.7
        assert reranker.batch_size == 2

    def test_rerank_empty_candidates(self):
        """测试空候选"""
        from src.reranker import LLMReranker

        reranker = LLMReranker()
        result = reranker.rerank("query", [])
        assert result == []

    @patch('src.reranker.DASHSCOPE_AVAILABLE', False)
    def test_rerank_no_dashscope(self):
        """测试无dashscope时的行为"""
        from src.reranker import LLMReranker

        reranker = LLMReranker()
        candidates = [
            {"chunk_id": "c1", "score": 0.9, "text": "text1"},
            {"chunk_id": "c2", "score": 0.8, "text": "text2"}
        ]
        result = reranker.rerank("query", candidates)
        # 应该按原分数排序
        assert len(result) == 2
        assert result[0]["chunk_id"] == "c1"

    def test_parse_score(self):
        """测试分数解析"""
        from src.reranker import LLMReranker

        reranker = LLMReranker()

        content1 = "分数: 8\n理由: 相关性强"
        assert reranker._parse_score(content1) == 8.0

        content2 = "Score: 9.5\nReason: very relevant"
        assert reranker._parse_score(content2) == 9.5

        content3 = "不相关"
        assert reranker._parse_score(content3) == 0


class TestJinaReranker:
    """JinaReranker测试"""

    def test_init(self):
        """测试初始化"""
        from src.reranker import JinaReranker

        reranker = JinaReranker(api_key="test_key", model="jina-reranker-v1-base-en")
        assert reranker.api_key == "test_key"
        assert reranker.model == "jina-reranker-v1-base-en"

    def test_rerank_empty(self):
        """测试空候选"""
        from src.reranker import JinaReranker

        reranker = JinaReranker()
        result = reranker.rerank("query", [])
        assert result == []

    def test_rerank_no_api_key(self):
        """测试无API Key时按分数排序"""
        from src.reranker import JinaReranker

        reranker = JinaReranker(api_key="")
        candidates = [
            {"chunk_id": "c1", "score": 0.5, "text": "text1"},
            {"chunk_id": "c2", "score": 0.9, "text": "text2"}
        ]
        result = reranker.rerank("query", candidates, top_n=2)
        # 应该按原分数排序
        assert result[0]["chunk_id"] == "c2"
        assert result[1]["chunk_id"] == "c1"


class TestRetrievalLogger:
    """RetrievalLogger测试"""

    def test_init(self):
        """测试初始化"""
        from src.retrieval_logger import RetrievalLogger

        logger = RetrievalLogger(log_dir="data/logs", log_level="INFO")
        assert logger.log_dir == Path("data/logs")
        assert logger.log_level == "INFO"

    def test_start_retrieval(self):
        """测试开始检索"""
        from src.retrieval_logger import RetrievalLogger

        logger = RetrievalLogger()
        log_id = logger.start_retrieval("测试查询")
        assert log_id.startswith("ret_")
        assert logger._current_log is not None

    def test_start_end_stage(self):
        """测试阶段记录"""
        from src.retrieval_logger import RetrievalLogger

        logger = RetrievalLogger()
        logger.start_retrieval("测试")

        logger.start_stage("query_rewrite", {"query": "测试"})
        logger.end_stage({"rewritten": "改写后"})

        assert len(logger._current_log.stages) == 1
        assert logger._current_log.stages[0]["name"] == "query_rewrite"
        assert logger._current_log.stages[0]["duration_ms"] is not None

    def test_finish_retrieval(self):
        """测试完成检索"""
        from src.retrieval_logger import RetrievalLogger

        logger = RetrievalLogger()
        logger.start_retrieval("测试")

        results = [{"chunk_id": "c1", "score": 0.9}]
        logger.finish_retrieval(results)

        assert len(logger._current_log.final_results) == 1

    def test_get_summary(self):
        """测试获取摘要"""
        from src.retrieval_logger import RetrievalLogger

        logger = RetrievalLogger()
        logger.start_retrieval("测试查询"*20)
        logger.start_stage("stage1")
        logger.end_stage({"data": 1})

        summary = logger.get_summary()
        assert "log_id" in summary
        assert "total_latency_ms" in summary


class TestIntegration:
    """集成测试"""

    def test_retrieval_pipeline_mock(self):
        """测试完整检索流程（mock）"""
        from src.retriever import HybridRetriever
        from src.reranker import LLMReranker
        from src.retrieval_logger import RetrievalLogger

        # 初始化
        retriever = HybridRetriever()
        reranker = LLMReranker()
        logger = RetrievalLogger(log_level="DEBUG")

        # 开始检索
        logger.start_retrieval("中芯国际2024年营收")
        logger.start_stage("retrieval")

        # Mock搜索结果
        mock_results = [
            {"chunk_id": "c1", "score": 0.9, "text": "营收500亿", "parent_id": "p1"},
            {"chunk_id": "c2", "score": 0.8, "text": "营收增长20%", "parent_id": "p1"},
        ]
        retriever._attach_parent_chunks(mock_results)

        logger.end_stage({"result_count": len(mock_results)})

        # 重排
        logger.start_stage("rerank")
        reranked = reranker.rerank("中芯国际2024年营收", mock_results)
        logger.end_stage({"result_count": len(reranked)})

        logger.finish_retrieval(reranked)
        logger.save()

        # 验证
        summary = logger.get_summary()
        assert summary["result_count"] == len(reranked)
        assert summary["total_latency_ms"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])