"""BM25索引模块"""
import json
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from tqdm import tqdm

try:
    from rank_bm25 import BM25Okapi
    BM25PlusOkapi = None  # BM25Plus not available in all versions
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False

import re


class BM25Index:
    """BM25索引"""

    def __init__(self, k1: float = 1.5, b: float = 0.75, use_plus: bool = False):
        """
        初始化BM25索引

        Args:
            k1: BM25 k1参数，控制词频饱和度
            b: BM25 b参数，控制文档长度归一化
            use_plus: 是否使用BM25+（更稳定的变体）
        """
        self.k1 = k1
        self.b = b
        self.use_plus = use_plus
        self._index = None
        self._tokenized_corpus = []
        self._chunk_ids = []
        self._metadata = []

    def index(self, texts: List[str], chunk_ids: List[str], metadata: Optional[List[Dict]] = None) -> None:
        """
        构建BM25索引

        Args:
            texts: 文本列表
            chunk_ids: 对应的chunk_id列表
            metadata: 可选的元数据列表
        """
        if not BM25_AVAILABLE:
            raise ImportError("rank_bm25未安装，请运行: pip install rank-bm25")

        # 分词
        self._tokenized_corpus = [self._tokenize(text) for text in tqdm(texts, desc="BM25分词")]
        self._chunk_ids = chunk_ids
        self._metadata = metadata or [{}] * len(texts)

        # 构建索引
        if self.use_plus and BM25PlusOkapi:
            self._index = BM25PlusOkapi(self._tokenized_corpus, k1=self.k1, b=self.b)
        else:
            self._index = BM25Okapi(self._tokenized_corpus, k1=self.k1, b=self.b)

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        搜索最相关的文本

        Args:
            query: 查询文本
            top_k: 返回数量

        Returns:
            [{"chunk_id": ..., "text": ..., "score": ..., "metadata": {...}}, ...]
        """
        if self._index is None:
            raise RuntimeError("BM25索引未构建，请先调用 index()")

        # 分词查询
        query_tokens = self._tokenize(query)

        # 计算分数
        scores = self._index.get_scores(query_tokens)

        # 获取top_k
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        results = []
        for rank, idx in enumerate(top_indices):
            results.append({
                "rank": rank + 1,
                "chunk_id": self._chunk_ids[idx],
                "score": float(scores[idx]),
                "metadata": self._metadata[idx]
            })

        return results

    def save(self, save_dir: str) -> None:
        """保存索引到磁盘"""
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        with open(save_dir / "bm25_index.pkl", "wb") as f:
            pickle.dump({
                "index": self._index,
                "tokenized_corpus": self._tokenized_corpus,
                "chunk_ids": self._chunk_ids,
                "metadata": self._metadata,
                "k1": self.k1,
                "b": self.b,
                "use_plus": self.use_plus
            }, f)

    def load(self, load_dir: str) -> None:
        """从磁盘加载索引"""
        load_dir = Path(load_dir)
        index_file = load_dir / "bm25_index.pkl"

        if not index_file.exists():
            raise FileNotFoundError(f"BM25索引文件不存在: {index_file}")

        with open(index_file, "rb") as f:
            data = pickle.load(f)
            self._index = data["index"]
            self._tokenized_corpus = data["tokenized_corpus"]
            self._chunk_ids = data["chunk_ids"]
            self._metadata = data["metadata"]
            self.k1 = data["k1"]
            self.b = data["b"]
            self.use_plus = data["use_plus"]

    def _tokenize(self, text: str) -> List[str]:
        """简单分词"""
        # 移除特殊字符，分割为单词
        text = re.sub(r'[^\w\u4e00-\u9fff]', ' ', text)  # 保留中文和英文
        text = text.lower()
        tokens = text.split()
        # 过滤太短的词
        return [t for t in tokens if len(t) >= 2]

    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        return {
            "total_documents": len(self._chunk_ids) if self._chunk_ids else 0,
            "k1": self.k1,
            "b": self.b,
            "use_plus": self.use_plus
        }


class BM25IndexManager:
    """BM25索引管理器"""

    def __init__(self):
        self.indices: Dict[str, BM25Index] = {}
        self.base_dir = "data/bm25"

    def create_index(self, name: str, **kwargs) -> BM25Index:
        """创建新的BM25索引"""
        index = BM25Index(**kwargs)
        self.indices[name] = index
        return index

    def get_index(self, name: str) -> Optional[BM25Index]:
        """获取索引"""
        return self.indices.get(name)

    def save_all(self) -> None:
        """保存所有索引"""
        for name, index in self.indices.items():
            index.save(Path(self.base_dir) / name)

    def load_all(self) -> None:
        """加载所有索引"""
        base = Path(self.base_dir)
        if not base.exists():
            return

        for index_dir in base.iterdir():
            if index_dir.is_dir():
                name = index_dir.name
                index = BM25Index()
                index.load(str(index_dir))
                self.indices[name] = index