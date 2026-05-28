"""检索配置"""
import os
from dataclasses import dataclass
from typing import List, Dict, Any
from .settings import BaseConfig


def _load_rules_from_yaml() -> List[Dict[str, Any]]:
    """从YAML加载query classification规则"""
    import yaml
    config_dir = os.path.dirname(os.path.abspath(__file__))
    yaml_path = os.path.join(config_dir, "query_types.yaml")
    if os.path.exists(yaml_path):
        with open(yaml_path, 'r', encoding='utf-8') as f:
            conf = yaml.safe_load(f)
        return conf.get("query_classification", {}).get("rules", [])
    return []


@dataclass
class RetrievalConfig(BaseConfig):
    """检索相关配置"""

    # 分块配置
    chunk_size: int = 500  # 子Chunk大小（字符数）
    chunk_overlap: int = 150  # 子Chunk重叠大小
    parent_chunk_size: int = 800  # 父Chunk大小
    enable_parent_retrieval: bool = True  # 是否启用父子关联

    # 检索配置
    bm25_weight: float = 0.3  # BM25权重
    vector_weight: float = 0.7  # Vector权重
    top_k_retrieval: int = 20  # 召回数量

    # MultiQuery配置
    enable_multiquery: bool = True  # 是否启用MultiQuery
    num_query_variants: int = 3  # 查询变体数量

    # Query Rewriter配置
    enable_query_rewrite: bool = True  # 是否启用查询改写

    # 重排配置
    enable_rerank: bool = True  # 是否启用重排
    rerank_top_k: int = 5  # 重排后返回数量
    llm_weight: float = 0.7  # LLM分数权重
    use_jina_reranker: bool = False  # 使用Jina替代LLM重排

    # 对话历史配置
    enable_history: bool = True  # 是否启用对话历史
    max_history_turns: int = 5  # 最大历史轮数
    history_strategy: str = "last_k"  # last_k / sliding_window / summary

    # 查询分类规则（从YAML加载，通用规则引擎解释）
    query_classification_rules: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.query_classification_rules is None:
            self.query_classification_rules = _load_rules_from_yaml()

    def validate(self) -> bool:
        """验证配置合法性"""
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if not 0 <= self.bm25_weight <= 1:
            raise ValueError("bm25_weight must be between 0 and 1")
        if not 0 <= self.vector_weight <= 1:
            raise ValueError("vector_weight must be between 0 and 1")
        if self.bm25_weight + self.vector_weight != 1.0:
            # 自动归一化
            total = self.bm25_weight + self.vector_weight
            self.bm25_weight /= total
            self.vector_weight /= total
        if self.history_strategy not in ["last_k", "sliding_window", "summary"]:
            raise ValueError("history_strategy must be one of: last_k, sliding_window, summary")
        return True