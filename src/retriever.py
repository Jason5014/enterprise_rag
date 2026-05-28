"""检索器模块 - 混合检索"""
import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

from config.retrieval_config import RetrievalConfig
from src.vector_store import VectorStore
from src.bm25_index import BM25Index


class HybridRetriever:
    """混合检索器 - 结合BM25和Vector"""

    def __init__(self, config: Optional[RetrievalConfig] = None):
        self.config = config or RetrievalConfig()
        self.bm25_weight = self.config.bm25_weight
        self.vector_weight = self.config.vector_weight
        self.top_k = self.config.top_k_retrieval
        self.enable_parent = self.config.enable_parent_retrieval

        self._vector_store: Optional[VectorStore] = None
        self._bm25_index: Optional[BM25Index] = None
        self._parent_chunks: Dict[str, Any] = {}
        self._chunk_texts: Dict[str, str] = {}  # chunk_id -> text 映射

    def load_index(self, index_dir: str = "data/chunked") -> None:
        """加载索引"""
        index_path = Path(index_dir)

        # 加载向量库
        vector_dir = index_path / "vector_db"
        if vector_dir.exists():
            try:
                self._vector_store = VectorStore()
                self._vector_store.load(str(vector_dir))
            except Exception as e:
                logger.error("向量库加载失败: %s", e)
                self._vector_store = None

        # 加载BM25
        bm25_dir = index_path / "bm25"
        if bm25_dir.exists():
            try:
                self._bm25_index = BM25Index()
                self._bm25_index.load(str(bm25_dir))
            except Exception as e:
                logger.error("BM25索引加载失败: %s", e)
                self._bm25_index = None

        # 加载父Chunk映射和chunk文本
        chunks_file = index_path / "chunks.json"
        if chunks_file.exists():
            with open(chunks_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 建立 parent_id -> parent_chunk 的映射
                for parent in data.get("parent_chunks", []):
                    self._parent_chunks[parent["chunk_id"]] = parent
                # 建立 chunk_id -> text 的映射（用于检索结果）
                for chunk in data.get("chunks", []):
                    self._chunk_texts[chunk["chunk_id"]] = chunk.get("text", "")

    def search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        混合搜索

        Args:
            query: 查询文本
            top_k: 返回数量

        Returns:
            List[Dict] - 检索结果列表
        """
        k = top_k or self.top_k

        bm25_results = []
        vector_results = []

        # BM25搜索
        if self._bm25_index:
            bm25_results = self._bm25_index.search(query, top_k=k * 2)
            for r in bm25_results:
                r["source"] = "bm25"

        # Vector搜索
        if self._vector_store:
            try:
                vector_results = self._vector_store.search(query, top_k=k * 2)
                for r in vector_results:
                    r["source"] = "vector"
            except Exception as e:
                logger.error("向量搜索失败: %s", e)
                vector_results = []

        # 融合结果
        fused = self._fuse_results(bm25_results, vector_results, k)

        # 如果启用PDR，获取父Chunk
        if self.enable_parent:
            fused = self._attach_parent_chunks(fused)

        return fused

    def _fuse_results(self, bm25_results: List[Dict], vector_results: List[Dict], top_k: int) -> List[Dict[str, Any]]:
        """融合BM25和Vector结果"""
        combined_scores: Dict[str, Dict[str, Any]] = {}

        # 处理BM25结果
        max_bm25_score = max((r["score"] for r in bm25_results), default=1.0)
        for r in bm25_results:
            chunk_id = r["chunk_id"]
            normalized_score = r["score"] / max_bm25_score if max_bm25_score > 0 else 0
            combined_scores[chunk_id] = {
                **r,
                "bm25_score": normalized_score,
                "vector_score": 0.0,
                "final_score": self.bm25_weight * normalized_score
            }

        # 处理Vector结果
        max_vector_score = max((r["score"] for r in vector_results), default=1.0)
        for r in vector_results:
            chunk_id = r["chunk_id"]
            normalized_score = r["score"] / max_vector_score if max_vector_score > 0 else 0

            if chunk_id in combined_scores:
                combined_scores[chunk_id]["vector_score"] = normalized_score
                combined_scores[chunk_id]["final_score"] = (
                    self.bm25_weight * combined_scores[chunk_id]["bm25_score"] +
                    self.vector_weight * normalized_score
                )
            else:
                combined_scores[chunk_id] = {
                    **r,
                    "bm25_score": 0.0,
                    "vector_score": normalized_score,
                    "final_score": self.vector_weight * normalized_score
                }

        # 排序
        sorted_results = sorted(
            combined_scores.values(),
            key=lambda x: x["final_score"],
            reverse=True
        )[:top_k]

        # 重新计算排名
        for i, r in enumerate(sorted_results):
            r["rank"] = i + 1
            r["score"] = r["final_score"]

        return sorted_results

    def _attach_parent_chunks(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """为结果附加父Chunk信息"""
        for r in results:
            chunk_id = r.get("chunk_id")

            # 优先使用_chunk_texts中的文本
            if chunk_id and chunk_id in self._chunk_texts:
                r["text"] = self._chunk_texts[chunk_id]

            # 从chunk_id推导parent_id（如果是child chunk）
            parent_id = r.get("parent_id")
            if not parent_id and chunk_id and "_child_" in chunk_id:
                parts = chunk_id.rsplit("_child_", 1)
                if len(parts) == 2:
                    parent_id = parts[0]
                    r["parent_id"] = parent_id

            if parent_id and parent_id in self._parent_chunks:
                r["parent_chunk"] = self._parent_chunks[parent_id]
                r["parent_text"] = self._parent_chunks[parent_id].get("text", "")
            else:
                r["parent_chunk"] = None
                if "parent_text" not in r:
                    r["parent_text"] = r.get("text", "")

        return results

    def get_retrieval_info(self) -> Dict[str, Any]:
        """获取检索器信息"""
        info = {
            "bm25_weight": self.bm25_weight,
            "vector_weight": self.vector_weight,
            "top_k": self.top_k,
            "enable_parent_retrieval": self.enable_parent
        }

        if self._vector_store:
            info["vector_stats"] = self._vector_store.get_stats()

        if self._bm25_index:
            info["bm25_stats"] = self._bm25_index.get_stats()

        info["parent_chunk_count"] = len(self._parent_chunks)

        return info