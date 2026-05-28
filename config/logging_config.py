"""日志配置 - 企业级日志架构"""
from dataclasses import dataclass, field
from typing import Dict, Optional
from .settings import BaseConfig


@dataclass
class LogConfig(BaseConfig):
    """日志配置"""

    # 全局日志级别
    level: str = "DEBUG"

    # 控制台输出
    console_enabled: bool = True
    console_level: str = "INFO"
    console_color: bool = True

    # 文件输出（旋转）
    file_enabled: bool = True
    file_level: str = "DEBUG"
    file_path: str = "data/logs/app.log"
    file_max_bytes: int = 10 * 1024 * 1024  # 10MB
    file_backup_count: int = 5

    # JSON 文件输出（旋转）
    json_enabled: bool = True
    json_level: str = "DEBUG"
    json_path: str = "data/logs/app.jsonl"
    json_max_bytes: int = 20 * 1024 * 1024  # 20MB
    json_backup_count: int = 3

    # 模块级别覆盖
    module_levels: Dict[str, str] = field(default_factory=dict)

    # 第三方库抑制级别
    third_party_level: str = "WARNING"

    def validate(self) -> bool:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        for attr in ["level", "console_level", "file_level", "json_level", "third_party_level"]:
            val = getattr(self, attr)
            if val.upper() not in valid_levels:
                return False
        return True
