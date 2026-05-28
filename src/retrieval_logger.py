"""检索过程日志模块"""
import json
import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class RetrievalStage:
    """检索阶段"""
    name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def finish(self, data: Optional[Dict[str, Any]] = None):
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        if data:
            self.data.update(data)


@dataclass
class RetrievalLog:
    """检索日志"""
    log_id: str
    timestamp: str
    query: str
    stages: List[Dict[str, Any]] = field(default_factory=list)
    latency_ms: Dict[str, float] = field(default_factory=dict)
    total_latency_ms: float = 0
    final_results: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RetrievalLogger:
    """检索日志记录器"""

    def __init__(self, log_dir: str = "data/logs", log_level: str = "INFO"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_level = log_level
        self._current_log: Optional[RetrievalLog] = None
        self._current_stage: Optional[RetrievalStage] = None

        self.levels = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}
        self._min_level = self.levels.get(log_level, 1)

    def _should_log(self, level: str) -> bool:
        return self.levels.get(level, 1) >= self._min_level

    def start_retrieval(self, query: str) -> str:
        """开始一轮检索"""
        log_id = f"ret_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(query) % 1000:03d}"
        self._current_log = RetrievalLog(
            log_id=log_id,
            timestamp=datetime.now().isoformat(),
            query=query
        )
        return log_id

    def start_stage(self, stage_name: str, data: Optional[Dict[str, Any]] = None) -> None:
        """开始一个阶段"""
        self._current_stage = RetrievalStage(
            name=stage_name,
            start_time=time.time(),
            data=data or {}
        )

    def end_stage(self, data: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> None:
        """结束当前阶段"""
        if self._current_stage:
            self._current_stage.finish(data)
            if error:
                self._current_stage.error = error

            if self._current_log:
                self._current_log.stages.append(asdict(self._current_stage))
                self._current_log.latency_ms[self._current_stage.name] = self._current_stage.duration_ms or 0

            self._current_stage = None

    def finish_retrieval(self, results: List[Dict[str, Any]]) -> None:
        """完成检索"""
        if self._current_log:
            self._current_log.final_results = results
            self._current_log.total_latency_ms = sum(self._current_log.latency_ms.values())

    def log_event(self, level: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        """记录事件"""
        if self._should_log(level):
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "level": level,
                "message": message,
                "data": data or {}
            }
            if self._current_log:
                self._current_log.metadata.setdefault("events", []).append(log_entry)

            # 同时打印
            logger.log(getattr(logging, level, logging.INFO), message)

    def save(self) -> Optional[str]:
        """保存日志到文件"""
        if not self._current_log:
            return None

        log_file = self.log_dir / f"{self._current_log.log_id}.json"
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(self._current_log.to_dict(), f, ensure_ascii=False, indent=2)

        return str(log_file)

    def get_summary(self) -> Dict[str, Any]:
        """获取当前日志摘要"""
        if not self._current_log:
            return {}

        return {
            "log_id": self._current_log.log_id,
            "query": self._current_log.query[:50] + "..." if len(self._current_log.query) > 50 else self._current_log.query,
            "stages": list(self._current_log.latency_ms.keys()),
            "latency_ms": self._current_log.latency_ms,
            "total_latency_ms": self._current_log.total_latency_ms,
            "result_count": len(self._current_log.final_results),
            "final_results": self._current_log.final_results,
            "stage_details": self._current_log.stages
        }

    def debug(self, message: str, data: Optional[Dict[str, Any]] = None):
        self.log_event("DEBUG", message, data)

    def info(self, message: str, data: Optional[Dict[str, Any]] = None):
        self.log_event("INFO", message, data)

    def warning(self, message: str, data: Optional[Dict[str, Any]] = None):
        self.log_event("WARNING", message, data)

    def error(self, message: str, data: Optional[Dict[str, Any]] = None):
        self.log_event("ERROR", message, data)


class RetrievalLoggerMixin:
    """检索日志混入类"""

    def __init__(self, *args, **kwargs):
        self._logger: Optional[RetrievalLogger] = None
        super().__init__(*args, **kwargs)

    def set_logger(self, logger: RetrievalLogger) -> None:
        self._logger = logger

    def _log_stage(self, name: str, start: bool = True, data: Optional[Dict[str, Any]] = None):
        if self._logger:
            if start:
                self._logger.start_stage(name, data)
            else:
                self._logger.end_stage(data)