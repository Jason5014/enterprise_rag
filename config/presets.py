"""预设配置"""
from typing import Dict, List
from .settings import ConfigBundle
from .retrieval_config import RetrievalConfig
from .answer_config import AnswerConfig
from .pdf_config import PDFConfig
from .embedding_config import EmbeddingConfig
from .eval_config import EvalConfig
from .indexer_config import IndexerConfig
from .logging_config import LogConfig


# 基础配置 - 最简单的RAG流程
BASE_CONFIG = ConfigBundle(
    retrieval=RetrievalConfig(
        chunk_size=500,
        chunk_overlap=150,
        enable_parent_retrieval=True,
        bm25_weight=0.3,
        vector_weight=0.7,
        top_k_retrieval=20,
        enable_multiquery=False,
        enable_query_rewrite=False,
        enable_rerank=False,
        enable_history=True,
        max_history_turns=3,
    ),
    answer=AnswerConfig(
        answer_model="qwen-turbo",
        temperature=0.1,
        enable_schema_routing=True,
    ),
    pdf=PDFConfig(
        parse_tables=True,
        extract_images=False,
    ),
    embedding=EmbeddingConfig(
        provider="dashscope",
        batch_size=100,
    ),
    logging=LogConfig(),
)

# 快速配置 - 追求速度
FAST_CONFIG = ConfigBundle(
    retrieval=RetrievalConfig(
        chunk_size=300,
        chunk_overlap=100,
        enable_parent_retrieval=False,
        bm25_weight=0.4,
        vector_weight=0.6,
        top_k_retrieval=10,
        enable_multiquery=False,
        enable_query_rewrite=False,
        enable_rerank=False,
        enable_history=False,
    ),
    answer=AnswerConfig(
        answer_model="qwen-turbo",
        temperature=0.1,
        enable_schema_routing=False,
    ),
    pdf=PDFConfig(
        parse_tables=False,
        extract_images=False,
    ),
    embedding=EmbeddingConfig(
        provider="dashscope",
        batch_size=200,
    ),
    logging=LogConfig(console_level="WARNING", file_level="INFO"),
)

# 精度配置 - 追求精度
PRECISION_CONFIG = ConfigBundle(
    retrieval=RetrievalConfig(
        chunk_size=500,
        chunk_overlap=150,
        enable_parent_retrieval=True,
        bm25_weight=0.3,
        vector_weight=0.7,
        top_k_retrieval=30,
        enable_multiquery=True,
        num_query_variants=5,
        enable_query_rewrite=True,
        enable_rerank=True,
        rerank_top_k=10,
        llm_weight=0.7,
        enable_history=True,
        max_history_turns=5,
    ),
    answer=AnswerConfig(
        answer_model="qwen-turbo",
        temperature=0.1,
        min_steps=5,
        min_words=150,
        enable_schema_routing=True,
    ),
    pdf=PDFConfig(
        parse_tables=True,
        extract_images=False,
        serialization_batch_size=5,
    ),
    embedding=EmbeddingConfig(
        provider="dashscope",
        batch_size=100,
    ),
    eval_config=EvalConfig(
        enabled=True,
        eval_top_k=[1, 3, 5, 10],
    ),
    logging=LogConfig(),
)

# 完整配置 - 包含所有功能
FULL_CONFIG = ConfigBundle(
    retrieval=RetrievalConfig(
        chunk_size=500,
        chunk_overlap=150,
        parent_chunk_size=800,
        enable_parent_retrieval=True,
        bm25_weight=0.3,
        vector_weight=0.7,
        top_k_retrieval=20,
        enable_multiquery=True,
        num_query_variants=3,
        enable_query_rewrite=True,
        enable_rerank=True,
        rerank_top_k=5,
        llm_weight=0.7,
        use_jina_reranker=False,
        enable_history=True,
        max_history_turns=5,
        history_strategy="last_k",
    ),
    answer=AnswerConfig(
        answer_model="qwen-turbo",
        temperature=0.1,
        max_tokens=2000,
        min_steps=5,
        min_words=150,
        enable_schema_routing=True,
    ),
    pdf=PDFConfig(
        parse_tables=True,
        extract_images=False,
        serialization_model="qwen-turbo",
        serialization_batch_size=5,
        max_workers=3,
    ),
    embedding=EmbeddingConfig(
        provider="dashscope",
        dashscope_model="text-embedding-v1",
        batch_size=100,
        max_workers=4,
        vector_dim=1024,
        normalize=True,
    ),
    eval_config=EvalConfig(
        enabled=True,
        eval_model="qwen-turbo",
        eval_top_k=[1, 3, 5],
        output_dir="data/eval_results",
        save_bad_cases=True,
    ),
    indexer=IndexerConfig(
        enable_incremental=True,
        check_interval=300,
        auto_reindex=False,
        log_level="INFO",
    ),
    logging=LogConfig(
        console_level="INFO",
        file_level="DEBUG",
        json_enabled=True,
    ),
)

# 配置注册表
PRESETS: Dict[str, ConfigBundle] = {
    "base": BASE_CONFIG,
    "fast": FAST_CONFIG,
    "precision": PRECISION_CONFIG,
    "full": FULL_CONFIG,
}


def get_preset(name: str) -> ConfigBundle:
    """获取指定名称的预设配置"""
    if name not in PRESETS:
        available = list(PRESETS.keys())
        raise ValueError(f"Preset '{name}' not found. Available: {available}")
    return PRESETS[name]


def list_presets() -> List[str]:
    """列出所有可用的预设配置"""
    return list(PRESETS.keys())
