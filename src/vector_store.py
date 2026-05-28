"""向量库模块 - 使用FAISS"""
import os
import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from tqdm import tqdm

try:
    import faiss
    import dashscope
    from dashscope import TextEmbedding
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

from config.embedding_config import EmbeddingConfig
from src.utils import get_api_key


class VectorStore:
    """向量库管理器"""

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or EmbeddingConfig()
        self.embedding_dim = self.config.vector_dim
        self.index_type = self.config.index_type
        self._index = None
        self._chunk_ids = []
        self._metadata = []

    @property
    def index(self) -> faiss.Index:
        if self._index is None:
            raise RuntimeError("向量库未初始化，请先调用 create_index() 或 load()")
        return self._index

    def create_index(self) -> None:
        """创建向量索引"""
        if not FAISS_AVAILABLE:
            raise ImportError("faiss未安装，请运行: pip install faiss-cpu")

        # 根据索引类型创建
        if self.index_type == "FlatIP":
            self._index = faiss.IndexFlatIP(self.embedding_dim)
        elif self.index_type == "FlatL2":
            self._index = faiss.IndexFlatL2(self.embedding_dim)
        elif self.index_type == "IVF":
            # IVF索引需要训练
            self._index = faiss.IndexIVFFlat(faiss.IndexFlatIP(self.embedding_dim), self.embedding_dim, 100)
        else:
            self._index = faiss.IndexFlatIP(self.embedding_dim)

    def add_texts(self, texts: List[str], chunk_ids: List[str], metadata: Optional[List[Dict]] = None) -> None:
        """
        添加文本到向量库

        Args:
            texts: 文本列表
            chunk_ids: 对应的chunk_id列表
            metadata: 可选的元数据列表
        """
        if self._index is None:
            self.create_index()

        # 生成embeddings
        embeddings = self._generate_embeddings(texts)

        # 归一化（如果使用内积）
        if self.index_type == "FlatIP" and self.config.normalize:
            embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

        # 添加到索引
        self._index.add(embeddings.astype(np.float32))
        self._chunk_ids.extend(chunk_ids)
        self._metadata.extend(metadata or [{}] * len(texts))

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        搜索最相似的文本

        Args:
            query: 查询文本
            top_k: 返回数量

        Returns:
            [{"chunk_id": ..., "text": ..., "score": ..., "metadata": {...}}, ...]
        """
        if self._index is None or self._index.ntotal == 0:
            raise RuntimeError("向量库为空，请先添加数据")

        # 生成查询embedding
        query_embedding = self._generate_embeddings([query])
        if self.index_type == "FlatIP" and self.config.normalize:
            query_embedding = query_embedding / np.linalg.norm(query_embedding, axis=1, keepdims=True)

        # 搜索
        scores, indices = self._index.search(query_embedding.astype(np.float32), min(top_k, self._index.ntotal))

        # 整理结果
        results = []
        for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
            if idx >= 0 and idx < len(self._chunk_ids):
                results.append({
                    "rank": i + 1,
                    "chunk_id": self._chunk_ids[idx],
                    "score": float(score),
                    "metadata": self._metadata[idx]
                })

        return results

    def save(self, save_dir: str) -> None:
        """保存向量库到磁盘"""
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        if self._index is not None:
            faiss.write_index(self._index, str(save_dir / "index.faiss"))

        with open(save_dir / "metadata.json", 'w', encoding='utf-8') as f:
            json.dump({
                "chunk_ids": self._chunk_ids,
                "metadata": self._metadata,
                "embedding_dim": self.embedding_dim,
                "index_type": self.index_type
            }, f, ensure_ascii=False, indent=2)

    def load(self, load_dir: str) -> None:
        """从磁盘加载向量库"""
        load_dir = Path(load_dir)

        index_file = load_dir / "index.faiss"
        if index_file.exists():
            self._index = faiss.read_index(str(index_file))

        metadata_file = load_dir / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._chunk_ids = data["chunk_ids"]
                self._metadata = data["metadata"]
                self.embedding_dim = data.get("embedding_dim", self.embedding_dim)
                self.index_type = data.get("index_type", self.index_type)

    def _generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """生成文本embedding"""
        if not FAISS_AVAILABLE:
            raise ImportError("dashscope未安装，请运行: pip install dashscope")

        api_key = self._get_api_key()
        if not api_key:
            raise ValueError("未设置DASHSCOPE_API_KEY环境变量")

        embeddings = []
        batch_size = min(self.config.batch_size, 10)  # DashScope限制单次最多10条

        for i in tqdm(range(0, len(texts), batch_size), desc="生成Embedding"):
            batch_texts = texts[i:i + batch_size]
            response = TextEmbedding.call(
                model=self.config.dashscope_model,
                input=batch_texts,
                api_key=api_key
            )

            if response.status_code == 200:
                batch_embeddings = [item["embedding"] for item in response.output["embeddings"]]
                embeddings.extend(batch_embeddings)
            else:
                raise RuntimeError(f"Embedding API调用失败: {response.message}")

        return np.array(embeddings)

    def _get_api_key(self) -> str:
        try:
            return get_api_key()
        except ValueError:
            return ""

    def get_stats(self) -> Dict[str, Any]:
        """获取向量库统计信息"""
        return {
            "total_vectors": self._index.ntotal if self._index else 0,
            "embedding_dim": self.embedding_dim,
            "index_type": self.index_type
        }


class VectorStoreManager:
    """向量库管理器 - 支持多文档"""

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or EmbeddingConfig()
        self.stores: Dict[str, VectorStore] = {}
        self.base_dir = "data/vector_db"

    def create_store(self, name: str) -> VectorStore:
        """创建新的向量库"""
        store = VectorStore(config=self.config)
        store.create_index()
        self.stores[name] = store
        return store

    def get_store(self, name: str) -> Optional[VectorStore]:
        """获取向量库"""
        return self.stores.get(name)

    def save_all(self) -> None:
        """保存所有向量库"""
        for name, store in self.stores.items():
            store.save(Path(self.base_dir) / name)

    def load_all(self) -> None:
        """加载所有向量库"""
        base = Path(self.base_dir)
        if not base.exists():
            return

        for store_dir in base.iterdir():
            if store_dir.is_dir():
                name = store_dir.name
                store = VectorStore(config=self.config)
                store.load(str(store_dir))
                self.stores[name] = store