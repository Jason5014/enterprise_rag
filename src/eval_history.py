"""评测历史管理模块 - 持久化评测结果，支持横向对比"""
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class EvalRecord:
    """评测记录"""
    eval_id: str
    timestamp: str
    config_name: str
    question_count: int
    metrics: Dict[str, float]           # recall@1, recall@3, recall@5, mrr, ndcg@5, faithfulness, relevance, completeness
    category_metrics: Dict[str, Dict]   # per-category metrics
    composite_score: float              # 综合评分 0-100
    llm_eval_enabled: bool
    config_snapshot: Optional[Dict[str, Any]] = None
    questions: Optional[List[str]] = None           # 测试问题列表
    query_results: Optional[List[Dict[str, Any]]] = None  # 逐题详情
    categories_meta: Optional[Dict[str, str]] = None  # 分类描述

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EvalHistory:
    """评测历史管理器"""

    def __init__(self, eval_dir: str = "data/eval_results"):
        self.eval_dir = Path(eval_dir)
        self.eval_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.eval_dir / "eval_history.jsonl"
        self._cache: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        """加载历史记录"""
        if self.history_file.exists():
            with open(self.history_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        try:
                            self._cache.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

    def save(
        self,
        config_name: str,
        question_count: int,
        metrics: Dict[str, float],
        category_metrics: Optional[Dict[str, Dict]] = None,
        composite_score: float = 0.0,
        llm_eval_enabled: bool = False,
        config_snapshot: Optional[Dict[str, Any]] = None,
        questions: Optional[List[str]] = None,
        query_results: Optional[List[Dict[str, Any]]] = None,
        categories_meta: Optional[Dict[str, str]] = None
    ) -> str:
        """
        保存评测结果

        Returns:
            eval_id
        """
        eval_id = f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        record = EvalRecord(
            eval_id=eval_id,
            timestamp=datetime.now().isoformat(),
            config_name=config_name,
            question_count=question_count,
            metrics=metrics,
            category_metrics=category_metrics or {},
            composite_score=composite_score,
            llm_eval_enabled=llm_eval_enabled,
            config_snapshot=config_snapshot,
            questions=questions,
            query_results=query_results,
            categories_meta=categories_meta
        )

        entry = record.to_dict()
        self._cache.append(entry)

        with open(self.history_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        logger.info("评测结果已保存: %s", eval_id)
        return eval_id

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近的评测记录"""
        return self._cache[-limit:]

    def get_by_config(self, config_name: str) -> List[Dict[str, Any]]:
        """按配置名筛选"""
        return [r for r in self._cache if r.get("config_name") == config_name]

    def get_latest(self, n: int = 1) -> List[Dict[str, Any]]:
        """获取最近n条记录"""
        return self._cache[-n:] if self._cache else []

    def get_comparison_data(self, metric_keys: List[str] = None) -> List[Dict[str, Any]]:
        """
        获取对比数据，用于趋势图

        Args:
            metric_keys: 要对比的指标列表，默认为常用指标

        Returns:
            适合绘图的扁平数据列表
        """
        if metric_keys is None:
            metric_keys = ["recall@5", "mrr", "faithfulness", "relevance", "completeness"]

        rows = []
        for record in self._cache:
            row = {
                "eval_id": record.get("eval_id", ""),
                "timestamp": record.get("timestamp", ""),
                "config_name": record.get("config_name", ""),
                "composite_score": record.get("composite_score", 0),
                "question_count": record.get("question_count", 0),
            }
            metrics = record.get("metrics", {})
            for key in metric_keys:
                row[key] = metrics.get(key, 0)
            rows.append(row)

        return rows

    def get_trend_summary(self) -> Dict[str, Any]:
        """获取趋势摘要"""
        if len(self._cache) < 2:
            return {"has_trend": False, "message": "至少需要2次评测记录才能显示趋势"}

        latest = self._cache[-1]
        previous = self._cache[-2]

        latest_metrics = latest.get("metrics", {})
        prev_metrics = previous.get("metrics", {})

        changes = {}
        for key in latest_metrics:
            if key in prev_metrics:
                diff = latest_metrics[key] - prev_metrics[key]
                changes[key] = {
                    "current": latest_metrics[key],
                    "previous": prev_metrics[key],
                    "diff": diff,
                    "improved": diff > 0
                }

        return {
            "has_trend": True,
            "latest_config": latest.get("config_name", ""),
            "previous_config": previous.get("config_name", ""),
            "latest_composite": latest.get("composite_score", 0),
            "previous_composite": previous.get("composite_score", 0),
            "metric_changes": changes
        }
