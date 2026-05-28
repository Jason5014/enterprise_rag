"""文本分块模块测试"""
import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestTextSplitter:
    """TextSplitter测试"""

    def test_chunk_creation(self):
        """测试Chunk创建"""
        from src.text_splitter import Chunk

        chunk = Chunk(
            text="测试文本",
            chunk_id="test_1",
            parent_id="parent_1",
            metadata={"page": 1}
        )
        assert chunk.text == "测试文本"
        assert chunk.chunk_id == "test_1"
        assert chunk.parent_id == "parent_1"
        assert chunk.metadata["page"] == 1

    def test_chunk_to_dict(self):
        """测试Chunk序列化"""
        from src.text_splitter import Chunk

        chunk = Chunk(text="测试", chunk_id="c1", parent_id="p1")
        d = chunk.to_dict()
        assert d["text"] == "测试"
        assert d["chunk_id"] == "c1"
        assert d["parent_id"] == "p1"

    def test_chunk_from_dict(self):
        """测试Chunk反序列化"""
        from src.text_splitter import Chunk

        d = {"text": "测试", "chunk_id": "c1", "parent_id": "p1", "metadata": {}}
        chunk = Chunk.from_dict(d)
        assert chunk.text == "测试"
        assert chunk.chunk_id == "c1"

    def test_parent_chunk_creation(self):
        """测试ParentChunk创建"""
        from src.text_splitter import ParentChunk

        parent = ParentChunk(
            text="父文本内容",
            parent_id="parent_1",
            metadata={"page": 1}
        )
        # ParentChunk的chunk_id等于parent_id，它自己就是父
        assert parent.chunk_id == "parent_1"
        # parent_id为None，因为父chunk没有父chunk
        assert parent.parent_id is None
        assert parent.text == "父文本内容"

    def test_split_simple_text(self):
        """测试简单文本分块"""
        from src.text_splitter import TextSplitter
        from config.retrieval_config import RetrievalConfig

        config = RetrievalConfig(
            chunk_size=100,
            chunk_overlap=20,
            parent_chunk_size=300,
            enable_parent_retrieval=True
        )
        splitter = TextSplitter(config=config)

        text = "这是测试文本" * 50  # 350字左右
        child_chunks, parent_chunks = splitter.split_text(text, "doc1")

        assert len(child_chunks) > 0
        assert len(parent_chunks) > 0
        # 每个子chunk应该有parent_id
        for chunk in child_chunks:
            assert chunk.parent_id is not None

    def test_split_short_text(self):
        """测试短文本不分块"""
        from src.text_splitter import TextSplitter

        splitter = TextSplitter()
        text = "短文本"
        child_chunks, parent_chunks = splitter.split_text(text, "doc1")

        assert len(child_chunks) >= 1
        assert len(parent_chunks) >= 1

    def test_split_empty_text(self):
        """测试空文本"""
        from src.text_splitter import TextSplitter

        splitter = TextSplitter()
        child_chunks, parent_chunks = splitter.split_text("", "doc1")

        assert len(child_chunks) == 0
        assert len(parent_chunks) == 0

    def test_split_documents(self):
        """测试批量分块"""
        from src.text_splitter import TextSplitter

        splitter = TextSplitter()
        documents = [
            {"text": "文档1内容" * 50, "doc_id": "doc1", "metadata": {"source": "test1"}},
            {"text": "文档2内容" * 50, "doc_id": "doc2", "metadata": {"source": "test2"}}
        ]

        result = splitter.split_documents(documents)

        assert "chunks" in result
        assert "parent_chunks" in result
        assert "metadata" in result
        assert result["metadata"]["total_docs"] == 2
        assert result["metadata"]["total_child_chunks"] > 0
        assert result["metadata"]["total_parent_chunks"] > 0

    def test_find_best_split_position(self):
        """测试最佳分割位置"""
        from src.text_splitter import TextSplitter

        splitter = TextSplitter()
        text = "第一段内容\n\n第二段内容\n\n第三段内容"
        pos = splitter._find_best_split_position(text)

        # 应该找到 \n\n 的位置
        assert pos > 0

    def test_parent_chunk_size_respected(self):
        """测试父Chunk大小限制"""
        from src.text_splitter import TextSplitter
        from config.retrieval_config import RetrievalConfig

        config = RetrievalConfig(
            parent_chunk_size=100,
            enable_parent_retrieval=True
        )
        splitter = TextSplitter(config=config)

        text = "测试" * 100  # 200字
        child_chunks, parent_chunks = splitter.split_text(text, "doc1")

        # 应该至少有2个父chunk
        assert len(parent_chunks) >= 2
        for parent in parent_chunks:
            assert len(parent.text) <= 110  # 允许一些余量


class TestRetrievalConfig:
    """RetrievalConfig测试"""

    def test_default_config(self):
        """测试默认配置"""
        from config.retrieval_config import RetrievalConfig

        config = RetrievalConfig()
        assert config.chunk_size == 500
        assert config.chunk_overlap == 150
        assert config.enable_parent_retrieval is True
        assert config.bm25_weight == 0.3
        assert config.vector_weight == 0.7

    def test_config_validation(self):
        """测试配置验证"""
        from config.retrieval_config import RetrievalConfig

        config = RetrievalConfig()
        assert config.validate() is True

    def test_config_normalization(self):
        """测试权重归一化"""
        from config.retrieval_config import RetrievalConfig

        config = RetrievalConfig(bm25_weight=0.6, vector_weight=0.6)
        config.validate()
        # 权重应该被归一化
        assert abs(config.bm25_weight - 0.5) < 0.01
        assert abs(config.vector_weight - 0.5) < 0.01


class TestBM25Index:
    """BM25Index测试"""

    def test_bm25_creation(self):
        """测试BM25创建"""
        from src.bm25_index import BM25Index

        bm25 = BM25Index(k1=1.5, b=0.75)
        assert bm25.k1 == 1.5
        assert bm25.b == 0.75
        assert bm25._index is None

    def test_bm25_index_documents(self):
        """测试BM25索引构建"""
        from src.bm25_index import BM25Index

        if not BM25Index.__module__.endswith('.bm25_index'):
            pytest.skip("BM25 not available")

        bm25 = BM25Index()
        texts = ["这是一个测试文档", "这是另一个文档", "测试文档的内容"]
        chunk_ids = ["c1", "c2", "c3"]

        bm25.index(texts, chunk_ids)
        assert bm25._index is not None

    def test_bm25_search(self):
        """测试BM25搜索"""
        from src.bm25_index import BM25Index

        bm25 = BM25Index()
        texts = ["苹果是水果", "香蕉是水果", "汽车是交通工具"]
        chunk_ids = ["c1", "c2", "c3"]
        metadata = [{"type": "fruit"}, {"type": "fruit"}, {"type": "vehicle"}]

        bm25.index(texts, chunk_ids, metadata)
        results = bm25.search("水果", top_k=2)

        assert len(results) == 2
        assert results[0]["chunk_id"] in ["c1", "c2"]
        assert results[0]["score"] > 0

    def test_bm25_tokenize(self):
        """测试分词"""
        from src.bm25_index import BM25Index

        bm25 = BM25Index()
        tokens = bm25._tokenize("这是一个测试")
        assert len(tokens) >= 1

    def test_bm25_stats(self):
        """测试统计信息"""
        from src.bm25_index import BM25Index

        bm25 = BM25Index()
        stats = bm25.get_stats()
        assert "total_documents" in stats
        assert "k1" in stats
        assert "b" in stats


class TestVectorStore:
    """VectorStore测试"""

    def test_vector_store_creation(self):
        """测试向量库创建"""
        from src.vector_store import VectorStore
        from config.embedding_config import EmbeddingConfig

        config = EmbeddingConfig(vector_dim=1024)
        store = VectorStore(config=config)
        assert store.embedding_dim == 1024

    def test_vector_store_stats(self):
        """测试统计信息"""
        from src.vector_store import VectorStore

        store = VectorStore()
        stats = store.get_stats()
        assert "total_vectors" in stats
        assert "embedding_dim" in stats


class TestIncrementalIndexer:
    """IncrementalIndexer测试"""

    def test_incremental_indexer_creation(self):
        """测试增量索引器创建"""
        from src.incremental_indexer import IncrementalIndexer
        from config.indexer_config import IndexerConfig

        config = IndexerConfig(pdf_watch_dir="data/pdf_reports")
        indexer = IncrementalIndexer(config=config)
        assert indexer.watch_dir == Path("data/pdf_reports")
        assert indexer.check_interval == 300

    def test_compute_file_hash(self):
        """测试文件哈希计算"""
        import tempfile
        from src.incremental_indexer import IncrementalIndexer

        indexer = IncrementalIndexer()

        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)

        try:
            hash1 = indexer.compute_file_hash(temp_path)
            assert len(hash1) == 16

            # 相同内容应该产生相同哈希
            hash2 = indexer.compute_file_hash(temp_path)
            assert hash1 == hash2
        finally:
            temp_path.unlink()

    def test_scan_directory_empty(self):
        """测试扫描空目录"""
        from src.incremental_indexer import IncrementalIndexer

        indexer = IncrementalIndexer()
        indexer.watch_dir = Path("/nonexistent")
        result = indexer.scan_directory()

        assert result["files"] == []
        assert result["total"] == 0

    def test_get_pending_changes_empty(self):
        """测试获取待处理变化（空）"""
        from src.incremental_indexer import IncrementalIndexer

        indexer = IncrementalIndexer()
        changes = indexer.get_pending_changes()
        assert isinstance(changes, list)


class TestIntegration:
    """集成测试"""

    def test_end_to_end_chunking(self):
        """端到端分块测试"""
        from src.text_splitter import TextSplitter

        splitter = TextSplitter()

        # 模拟文档
        documents = [
            {"text": "第1页的内容" * 100, "doc_id": "d1", "metadata": {"page": 1}},
            {"text": "第2页的内容" * 100, "doc_id": "d2", "metadata": {"page": 2}}
        ]

        result = splitter.split_documents(documents)

        assert result["metadata"]["total_docs"] == 2
        assert result["metadata"]["total_child_chunks"] > 0
        assert result["metadata"]["total_parent_chunks"] > 0

        # 检查JSON序列化
        json_str = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert len(parsed["chunks"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])