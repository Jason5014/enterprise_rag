"""增量索引配置"""
from dataclasses import dataclass
from .settings import BaseConfig


@dataclass
class IndexerConfig(BaseConfig):
    """增量索引相关配置"""

    # 增量索引开关
    enable_incremental: bool = True

    # 监控配置
    pdf_watch_dir: str = "data/pdf_reports"
    check_interval: int = 300  # 秒

    # 自动重索引
    auto_reindex: bool = False
    reindex_threshold: float = 0.3  # 变化比例超过30%时触发全量重建

    # 日志配置
    log_level: str = "INFO"  # DEBUG / INFO / WARNING / ERROR
    log_file: str = "data/logs/indexer.log"

    def validate(self) -> bool:
        """验证配置合法性"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        if self.log_level not in valid_levels:
            raise ValueError(f"log_level must be one of: {valid_levels}")
        if self.check_interval <= 0:
            raise ValueError("check_interval must be positive")
        if not 0 <= self.reindex_threshold <= 1:
            raise ValueError("reindex_threshold must be between 0 and 1")
        return True
