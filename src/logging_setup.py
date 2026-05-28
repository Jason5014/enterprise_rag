"""集中式日志初始化 - 企业级日志架构"""
import logging
import logging.handlers
import json
import os
import sys
from datetime import datetime
from typing import Optional

from config.logging_config import LogConfig


class ColorFormatter(logging.Formatter):
    """彩色控制台格式化器"""

    COLORS = {
        "DEBUG": "\033[36m",     # 青色
        "INFO": "\033[32m",      # 绿色
        "WARNING": "\033[33m",   # 黄色
        "ERROR": "\033[31m",     # 红色
        "CRITICAL": "\033[35m",  # 紫色
    }
    RESET = "\033[0m"

    def __init__(self, use_color: bool = True):
        super().__init__()
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        levelname = record.levelname
        if self.use_color and levelname in self.COLORS:
            colored_level = f"{self.COLORS[levelname]}{levelname}{self.RESET}"
        else:
            colored_level = levelname

        msg = record.getMessage()
        return f"[{colored_level}] {record.name} - {msg}"


class JSONFormatter(logging.Formatter):
    """JSON 行格式化器"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


_initialized = False


def init_logging(config: Optional[LogConfig] = None) -> None:
    """
    初始化日志系统（幂等）

    Args:
        config: 日志配置，为 None 时使用默认配置
    """
    global _initialized

    if config is None:
        config = LogConfig()

    root = logging.getLogger()

    # 清除已有 handlers（幂等）
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()

    root.setLevel(getattr(logging, config.level.upper(), logging.DEBUG))

    # 控制台 handler
    if config.console_enabled:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(getattr(logging, config.console_level.upper(), logging.INFO))
        console_handler.setFormatter(ColorFormatter(use_color=config.console_color))
        root.addHandler(console_handler)

    # 确保日志目录存在
    log_dir = os.path.dirname(config.file_path) or "data/logs"
    os.makedirs(log_dir, exist_ok=True)

    # 文件 handler（旋转）
    if config.file_enabled:
        file_handler = logging.handlers.RotatingFileHandler(
            config.file_path,
            maxBytes=config.file_max_bytes,
            backupCount=config.file_backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, config.file_level.upper(), logging.DEBUG))
        file_handler.setFormatter(logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        root.addHandler(file_handler)

    # JSON 文件 handler（旋转）
    if config.json_enabled:
        json_handler = logging.handlers.RotatingFileHandler(
            config.json_path,
            maxBytes=config.json_max_bytes,
            backupCount=config.json_backup_count,
            encoding="utf-8",
        )
        json_handler.setLevel(getattr(logging, config.json_level.upper(), logging.DEBUG))
        json_handler.setFormatter(JSONFormatter())
        root.addHandler(json_handler)

    # 模块级别覆盖
    for module_name, level_str in config.module_levels.items():
        module_logger = logging.getLogger(module_name)
        module_logger.setLevel(getattr(logging, level_str.upper(), logging.DEBUG))

    # 抑制第三方库日志
    for lib in ["httpx", "httpcore", "urllib3", "requests", "dashscope"]:
        logging.getLogger(lib).setLevel(
            getattr(logging, config.third_party_level.upper(), logging.WARNING)
        )

    _initialized = True
    logging.getLogger(__name__).info("日志系统初始化完成")
