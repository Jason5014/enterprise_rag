"""Embedding配置"""
from dataclasses import dataclass
from .settings import BaseConfig


@dataclass
class EmbeddingConfig(BaseConfig):
    """Embedding相关配置"""

    # Embedding 提供商配置
    provider: str = "dashscope"  # dashscope / openai / local

    # DashScope配置
    dashscope_model: str = "text-embedding-v3"

    # OpenAI配置
    openai_model: str = "text-embedding-3-small"
    openai_api_base: str = "https://api.openai.com/v1"

    # 本地Embedder配置
    local_model: str = "bge-large-zh"
    local_device: str = "cpu"  # cpu / cuda

    # 通用配置
    batch_size: int = 10  # 批量大小（DashScope限制单次最多25条，实际建议不超过10条）
    max_workers: int = 4  # 并行工作数

    # 向量库配置
    vector_dim: int = 1024  # 向量维度
    normalize: bool = True  # 是否归一化
    index_type: str = "FlatIP"  # FAISS索引类型

    def validate(self) -> bool:
        """验证配置合法性"""
        if self.provider not in ["dashscope", "openai", "local"]:
            raise ValueError("provider must be one of: dashscope, openai, local")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if self.vector_dim <= 0:
            raise ValueError("vector_dim must be positive")
        return True
