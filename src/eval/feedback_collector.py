"""反馈收集模块 - 收集和管理用户反馈"""
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
import uuid


@dataclass
class FeedbackEntry:
    """反馈条目"""
    feedback_id: str
    timestamp: str
    query: str
    answer: str
    step_by_step_analysis: Optional[str]
    reasoning_summary: Optional[str]
    relevant_pages: List[int]
    user_feedback: Dict[str, Any]
    session_id: str
    config_name: str
    retrieval_log_id: Optional[str] = None
    config_snapshot: Optional[Dict[str, Any]] = None
    retrieval_results: Optional[List[Dict[str, Any]]] = None
    comment: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FeedbackCollector:
    """用户反馈收集器"""

    def __init__(self, feedback_dir: str = "data/feedback"):
        self.feedback_dir = Path(feedback_dir)
        self.feedback_dir.mkdir(parents=True, exist_ok=True)
        self.feedback_file = self.feedback_dir / "feedback.jsonl"
        self._feedback_cache: List[Dict[str, Any]] = []
        self._load_feedback()

    def _load_feedback(self) -> None:
        """加载已有反馈"""
        if self.feedback_file.exists():
            with open(self.feedback_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        try:
                            self._feedback_cache.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

    def _save_feedback(self, entry: Dict[str, Any]) -> None:
        """保存单条反馈"""
        with open(self.feedback_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def collect(
        self,
        query: str,
        answer: str,
        step_by_step_analysis: Optional[str] = None,
        reasoning_summary: Optional[str] = None,
        relevant_pages: Optional[List[int]] = None,
        helpful: bool = True,
        rating: int = 0,
        correct_answer: Optional[str] = None,
        error_type: Optional[str] = None,
        session_id: str = "",
        config_name: str = "base",
        retrieval_log_id: Optional[str] = None,
        config_snapshot: Optional[Dict[str, Any]] = None,
        retrieval_results: Optional[List[Dict[str, Any]]] = None,
        comment: Optional[str] = None
    ) -> str:
        """
        收集用户反馈

        Args:
            query: 用户问题
            answer: 系统回答
            step_by_step_analysis: 推理过程
            reasoning_summary: 推理摘要
            relevant_pages: 引用的页码
            helpful: 是否有帮助
            rating: 评分 1-5
            correct_answer: 用户纠正的正确答案
            error_type: 错误类型
            session_id: 会话ID
            config_name: 使用的配置名称
            retrieval_log_id: 关联的检索日志ID
            config_snapshot: 当前配置快照
            retrieval_results: 检索结果摘要
            comment: 用户评论

        Returns:
            feedback_id
        """
        feedback_id = f"fb_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"

        entry = FeedbackEntry(
            feedback_id=feedback_id,
            timestamp=datetime.now().isoformat(),
            query=query,
            answer=answer,
            step_by_step_analysis=step_by_step_analysis,
            reasoning_summary=reasoning_summary,
            relevant_pages=relevant_pages or [],
            user_feedback={
                "helpful": helpful,
                "rating": rating,
                "correct_answer": correct_answer,
                "error_type": error_type
            },
            session_id=session_id,
            config_name=config_name,
            retrieval_log_id=retrieval_log_id,
            config_snapshot=config_snapshot,
            retrieval_results=retrieval_results,
            comment=comment
        )

        entry_dict = entry.to_dict()
        self._feedback_cache.append(entry_dict)
        self._save_feedback(entry_dict)

        return feedback_id

    def get_recent_feedback(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近的反馈"""
        return self._feedback_cache[-limit:]

    def get_bad_cases(
        self,
        min_rating: int = 3,
        unhelpful_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        获取Bad Cases（低质量回答）

        Args:
            min_rating: 最大评分阈值
            unhelpful_only: 只返回标记为不有帮助的

        Returns:
            Bad Cases列表
        """
        bad_cases = []
        for fb in self._feedback_cache:
            feedback = fb.get("user_feedback", {})

            is_bad = False
            if unhelpful_only and not feedback.get("helpful", True):
                is_bad = True
            if feedback.get("rating", 0) < min_rating and feedback.get("rating", 0) > 0:
                is_bad = True
            if feedback.get("error_type"):
                is_bad = True

            if is_bad:
                bad_cases.append(fb)

        return bad_cases

    def analyze_feedback(self) -> Dict[str, Any]:
        """
        分析反馈数据

        Returns:
            反馈分析统计
        """
        if not self._feedback_cache:
            return {
                "total": 0,
                "helpful_count": 0,
                "unhelpful_count": 0,
                "avg_rating": 0,
                "error_types": {},
                "by_config": {}
            }

        total = len(self._feedback_cache)
        helpful_count = sum(1 for f in self._feedback_cache if f.get("user_feedback", {}).get("helpful", False))
        unhelpful_count = total - helpful_count

        ratings = [f.get("user_feedback", {}).get("rating", 0) for f in self._feedback_cache if f.get("user_feedback", {}).get("rating", 0) > 0]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0

        error_types = {}
        for f in self._feedback_cache:
            et = f.get("user_feedback", {}).get("error_type")
            if et:
                error_types[et] = error_types.get(et, 0) + 1

        by_config = {}
        for f in self._feedback_cache:
            config = f.get("config_name", "unknown")
            if config not in by_config:
                by_config[config] = {"total": 0, "helpful": 0}
            by_config[config]["total"] += 1
            if f.get("user_feedback", {}).get("helpful"):
                by_config[config]["helpful"] += 1

        return {
            "total": total,
            "helpful_count": helpful_count,
            "unhelpful_count": unhelpful_count,
            "helpful_rate": helpful_count / total if total > 0 else 0,
            "avg_rating": avg_rating,
            "error_types": error_types,
            "error_type_count": len(error_types),
            "by_config": by_config,
            "bad_case_count": len(self.get_bad_cases())
        }

    def export_bad_cases(self, output_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        导出Bad Cases用于分析

        Args:
            output_path: 可选的输出路径

        Returns:
            Bad Cases列表
        """
        bad_cases = self.get_bad_cases()

        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(bad_cases, f, ensure_ascii=False, indent=2)

        return bad_cases

    def get_config_comparison(self) -> Dict[str, Dict[str, Any]]:
        """
        获取不同配置的效果对比

        Returns:
            配置效果对比字典
        """
        config_stats = {}

        for fb in self._feedback_cache:
            config = fb.get("config_name", "unknown")
            feedback = fb.get("user_feedback", {})

            if config not in config_stats:
                config_stats[config] = {
                    "total": 0,
                    "helpful": 0,
                    "unhelpful": 0,
                    "ratings": [],
                    "error_types": {}
                }

            config_stats[config]["total"] += 1

            if feedback.get("helpful"):
                config_stats[config]["helpful"] += 1
            else:
                config_stats[config]["unhelpful"] += 1

            rating = feedback.get("rating", 0)
            if rating > 0:
                config_stats[config]["ratings"].append(rating)

            et = feedback.get("error_type")
            if et:
                config_stats[config]["error_types"][et] = config_stats[config]["error_types"].get(et, 0) + 1

        # 计算汇总统计
        result = {}
        for config, stats in config_stats.items():
            avg_rating = sum(stats["ratings"]) / len(stats["ratings"]) if stats["ratings"] else 0
            helpful_rate = stats["helpful"] / stats["total"] if stats["total"] > 0 else 0

            result[config] = {
                "total_questions": stats["total"],
                "helpful_rate": helpful_rate,
                "avg_rating": avg_rating,
                "top_errors": sorted(stats["error_types"].items(), key=lambda x: -x[1])[:3]
            }

        return result