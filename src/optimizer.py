"""优化器 - 基于评估结果自动调优配置"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from config.retrieval_config import RetrievalConfig
from config.answer_config import AnswerConfig
from config.settings import ConfigBundle

logger = logging.getLogger(__name__)


@dataclass
class OptimizationSuggestion:
    """优化建议"""
    category: str          # 分类: retrieval, answer, chunk, rerank
    priority: str          # 优先级: high, medium, low
    metric: str            # 相关指标
    current_value: float   # 当前值
    target_value: float    # 目标值
    suggestion: str        # 建议描述
    config_changes: Dict[str, Any]  # 建议的配置修改


class RAGOptimizer:
    """RAG系统优化器"""

    def __init__(self, eval_results_dir: str = "data/eval_results", logs_dir: str = "data/logs"):
        self.eval_results_dir = Path(eval_results_dir)
        self.logs_dir = Path(logs_dir)

    def analyze_eval_results(self, eval_file: Optional[str] = None) -> Dict[str, Any]:
        """
        分析评估结果

        Args:
            eval_file: 指定评估文件路径，None则使用最新的

        Returns:
            分析结果
        """
        # 加载评估结果
        if eval_file:
            with open(eval_file, 'r', encoding='utf-8') as f:
                eval_data = json.load(f)
        else:
            eval_data = self._load_latest_eval()

        if not eval_data:
            return {"error": "未找到评估结果"}

        # 分析各个维度
        analysis = {
            "eval_file": eval_file or "latest",
            "timestamp": eval_data.get("timestamp"),
            "config": eval_data.get("config"),
            "questions_count": eval_data.get("questions_count", 0),
        }

        # 分析检索结果
        results = eval_data.get("results", [])
        if results:
            analysis["retrieval_analysis"] = self._analyze_retrieval(results)

        # 分析指标
        metrics = eval_data.get("metrics", {})
        if metrics:
            analysis["metrics_analysis"] = self._analyze_metrics(metrics)

        # 生成优化建议
        analysis["suggestions"] = self._generate_suggestions(analysis)

        return analysis

    def analyze_retrieval_logs(self, last_n: int = 10) -> Dict[str, Any]:
        """
        分析检索日志

        Args:
            last_n: 分析最近N条日志

        Returns:
            分析结果
        """
        log_files = sorted(self.logs_dir.glob("ret_*.json"), reverse=True)[:last_n]

        if not log_files:
            return {"error": "未找到检索日志"}

        analyses = []
        for log_file in log_files:
            with open(log_file, 'r', encoding='utf-8') as f:
                log_data = json.load(f)

            analysis = {
                "log_id": log_data.get("log_id"),
                "query": log_data.get("query"),
                "total_latency_ms": log_data.get("total_latency_ms", 0),
                "stages": {},
                "issues": []
            }

            # 分析各阶段
            for stage in log_data.get("stages", []):
                stage_name = stage.get("name")
                duration_ms = stage.get("duration_ms", 0)
                analysis["stages"][stage_name] = {
                    "duration_ms": duration_ms,
                    "has_error": stage.get("error") is not None
                }

                # 检测问题
                if duration_ms > 1000:
                    analysis["issues"].append(f"{stage_name} 耗时过长: {duration_ms:.0f}ms")
                if stage.get("error"):
                    analysis["issues"].append(f"{stage_name} 出错: {stage.get('error')}")

            analyses.append(analysis)

        # 汇总统计
        summary = self._summarize_log_analyses(analyses)

        return {
            "logs_analyzed": len(analyses),
            "analyses": analyses,
            "summary": summary
        }

    def _load_latest_eval(self) -> Optional[Dict]:
        """加载最新的评估结果"""
        eval_files = sorted(self.eval_results_dir.glob("eval_*.json"), reverse=True)
        if not eval_files:
            return None

        with open(eval_files[0], 'r', encoding='utf-8') as f:
            return json.load(f)

    def _analyze_retrieval(self, results: List[Dict]) -> Dict[str, Any]:
        """分析检索结果"""
        latencies = [r.get("latency_ms", 0) for r in results]
        top1_ids = [r.get("top1_relevant") for r in results if r.get("top1_relevant")]

        return {
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
            "max_latency_ms": max(latencies) if latencies else 0,
            "min_latency_ms": min(latencies) if latencies else 0,
            "slow_queries": [r for r in results if r.get("latency_ms", 0) > 2000],
            "total_queries": len(results)
        }

    def _analyze_metrics(self, metrics: Dict[str, float]) -> Dict[str, Any]:
        """分析评估指标"""
        analysis = {}

        # Recall 分析
        recall_1 = metrics.get("recall@1", 0)
        recall_5 = metrics.get("recall@5", 0)
        recall_10 = metrics.get("recall@10", 0)

        analysis["recall"] = {
            "recall@1": recall_1,
            "recall@5": recall_5,
            "recall@10": recall_10,
            "gap_1_5": recall_5 - recall_1,
            "gap_5_10": recall_10 - recall_5,
            "status": "good" if recall_5 >= 0.7 else "needs_improvement"
        }

        # MRR 分析
        mrr = metrics.get("mrr", 0)
        analysis["mrr"] = {
            "value": mrr,
            "status": "good" if mrr >= 0.5 else "needs_improvement"
        }

        # NDCG 分析
        ndcg = metrics.get("ndcg@5", 0)
        analysis["ndcg"] = {
            "value": ndcg,
            "status": "good" if ndcg >= 0.6 else "needs_improvement"
        }

        return analysis

    def _generate_suggestions(self, analysis: Dict[str, Any]) -> List[OptimizationSuggestion]:
        """生成优化建议"""
        suggestions = []

        metrics_analysis = analysis.get("metrics_analysis", {})
        retrieval_analysis = analysis.get("retrieval_analysis", {})

        # 1. Recall@5 偏低
        recall_analysis = metrics_analysis.get("recall", {})
        recall_5 = recall_analysis.get("recall@5", 0)
        if recall_5 < 0.7:
            gap = recall_analysis.get("gap_1_5", 0)
            if gap > 0.3:
                # Recall@1 和 Recall@5 差距大，说明相关文档排名靠后
                suggestions.append(OptimizationSuggestion(
                    category="rerank",
                    priority="high",
                    metric="recall@5",
                    current_value=recall_5,
                    target_value=0.7,
                    suggestion="Recall@1和@5差距大，相关文档排名靠后，建议启用或加强重排",
                    config_changes={
                        "retrieval.enable_rerank": True,
                        "retrieval.rerank_top_k": 10,
                        "retrieval.llm_weight": 0.7
                    }
                ))
            else:
                # 整体召回率低，需要增加检索范围
                suggestions.append(OptimizationSuggestion(
                    category="retrieval",
                    priority="high",
                    metric="recall@5",
                    current_value=recall_5,
                    target_value=0.7,
                    suggestion="整体召回率偏低，建议增加检索数量或启用MultiQuery",
                    config_changes={
                        "retrieval.top_k_retrieval": 30,
                        "retrieval.enable_multiquery": True,
                        "retrieval.num_query_variants": 3
                    }
                ))

        # 2. MRR 偏低
        mrr = metrics_analysis.get("mrr", {}).get("value", 0)
        if mrr < 0.5:
            suggestions.append(OptimizationSuggestion(
                category="rerank",
                priority="medium",
                metric="mrr",
                current_value=mrr,
                target_value=0.5,
                suggestion="首个结果相关性低，建议调整重排权重",
                config_changes={
                    "retrieval.enable_rerank": True,
                    "retrieval.llm_weight": 0.8
                }
            ))

        # 3. 延迟过高
        avg_latency = retrieval_analysis.get("avg_latency_ms", 0)
        if avg_latency > 2000:
            suggestions.append(OptimizationSuggestion(
                category="performance",
                priority="medium",
                metric="latency",
                current_value=avg_latency,
                target_value=1000,
                suggestion="检索延迟过高，建议减少top_k或禁用耗时功能",
                config_changes={
                    "retrieval.top_k_retrieval": 10,
                    "retrieval.enable_multiquery": False,
                    "retrieval.enable_rerank": False
                }
            ))

        # 4. Recall@1 和 @10 差距大
        recall_1 = recall_analysis.get("recall@1", 0)
        recall_10 = recall_analysis.get("recall@10", 0)
        if recall_10 - recall_1 > 0.4:
            suggestions.append(OptimizationSuggestion(
                category="chunk",
                priority="medium",
                metric="recall_gap",
                current_value=recall_10 - recall_1,
                target_value=0.2,
                suggestion="相关文档分散在多个Chunk中，建议调整分块策略或启用Query改写",
                config_changes={
                    "retrieval.enable_query_rewrite": True,
                    "retrieval.chunk_size": 500,
                    "retrieval.chunk_overlap": 150
                }
            ))

        return suggestions

    def _summarize_log_analyses(self, analyses: List[Dict]) -> Dict[str, Any]:
        """汇总日志分析"""
        if not analyses:
            return {}

        total_latencies = [a.get("total_latency_ms", 0) for a in analyses]
        all_issues = []
        for a in analyses:
            all_issues.extend(a.get("issues", []))

        # 统计各阶段平均耗时
        stage_times = {}
        for a in analyses:
            for stage_name, stage_data in a.get("stages", {}).items():
                if stage_name not in stage_times:
                    stage_times[stage_name] = []
                stage_times[stage_name].append(stage_data.get("duration_ms", 0))

        avg_stage_times = {
            name: sum(times) / len(times) if times else 0
            for name, times in stage_times.items()
        }

        return {
            "avg_latency_ms": sum(total_latencies) / len(total_latencies) if total_latencies else 0,
            "max_latency_ms": max(total_latencies) if total_latencies else 0,
            "total_issues": len(all_issues),
            "issue_counts": {issue: all_issues.count(issue) for issue in set(all_issues)},
            "avg_stage_times": avg_stage_times,
            "bottleneck": max(avg_stage_times.items(), key=lambda x: x[1])[0] if avg_stage_times else None
        }

    def apply_suggestions(
        self,
        config: ConfigBundle,
        suggestions: List[OptimizationSuggestion],
        auto_apply: bool = False
    ) -> Tuple[ConfigBundle, List[str]]:
        """
        应用优化建议

        Args:
            config: 当前配置
            suggestions: 优化建议列表
            auto_apply: 是否自动应用

        Returns:
            (新配置, 应用的变更列表)
        """
        changes = []
        new_config = config

        for suggestion in suggestions:
            if suggestion.priority == "high" or auto_apply:
                for key, value in suggestion.config_changes.items():
                    parts = key.split(".")
                    if len(parts) == 2:
                        config_name, attr_name = parts
                        config_obj = getattr(new_config, config_name, None)
                        if config_obj and hasattr(config_obj, attr_name):
                            old_value = getattr(config_obj, attr_name)
                            if old_value != value:
                                setattr(config_obj, attr_name, value)
                                changes.append(f"{key}: {old_value} -> {value}")

        return new_config, changes

    def diagnose(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        系统化诊断

        Args:
            analysis: 分析结果

        Returns:
            诊断结果，包含问题、根因、解决方案
        """
        diagnosis = {
            "problems": [],
            "root_causes": [],
            "solutions": []
        }

        metrics = analysis.get("metrics_analysis", {})
        recall = metrics.get("recall", {})
        mrr = metrics.get("mrr", {})
        ndcg = metrics.get("ndcg", {})
        retrieval = analysis.get("retrieval_analysis", {})

        recall_1 = recall.get("recall@1", 0)
        recall_5 = recall.get("recall@5", 0)
        recall_10 = recall.get("recall@10", 0)
        mrr_val = mrr.get("value", 0)
        gap_1_5 = recall.get("gap_1_5", 0)
        gap_5_10 = recall.get("gap_5_10", 0)

        # 诊断逻辑
        if recall_5 < 0.6:
            diagnosis["problems"].append({
                "name": "召回率严重不足",
                "metric": "recall@5",
                "value": recall_5,
                "severity": "critical"
            })

            if recall_10 < 0.7:
                diagnosis["root_causes"].append({
                    "cause": "检索范围不足",
                    "evidence": f"Recall@10={recall_10:.2f} 也偏低",
                    "category": "retrieval"
                })
                diagnosis["solutions"].append({
                    "action": "增加检索数量",
                    "config": {"retrieval.top_k_retrieval": 30},
                    "priority": "high",
                    "expected_improvement": "Recall@5 +15-20%"
                })
                diagnosis["solutions"].append({
                    "action": "启用MultiQuery扩展查询",
                    "config": {
                        "retrieval.enable_multiquery": True,
                        "retrieval.num_query_variants": 3
                    },
                    "priority": "high",
                    "expected_improvement": "Recall@5 +10-15%"
                })
            else:
                diagnosis["root_causes"].append({
                    "cause": "相关文档排名靠后",
                    "evidence": f"Recall@10={recall_10:.2f} 正常，但 Recall@5={recall_5:.2f} 低",
                    "category": "ranking"
                })
                diagnosis["solutions"].append({
                    "action": "启用重排",
                    "config": {
                        "retrieval.enable_rerank": True,
                        "retrieval.rerank_top_k": 10,
                        "retrieval.llm_weight": 0.7
                    },
                    "priority": "high",
                    "expected_improvement": "Recall@5 +10-15%, MRR +20%"
                })

        elif recall_5 < 0.7:
            diagnosis["problems"].append({
                "name": "召回率偏低",
                "metric": "recall@5",
                "value": recall_5,
                "severity": "warning"
            })

            if gap_1_5 > 0.25:
                diagnosis["root_causes"].append({
                    "cause": "相关文档排名靠后",
                    "evidence": f"Recall@1={recall_1:.2f} 和 Recall@5={recall_5:.2f} 差距大",
                    "category": "ranking"
                })
                diagnosis["solutions"].append({
                    "action": "启用或加强重排",
                    "config": {
                        "retrieval.enable_rerank": True,
                        "retrieval.llm_weight": 0.8
                    },
                    "priority": "medium",
                    "expected_improvement": "MRR +15-20%"
                })

        # MRR 诊断
        if mrr_val < 0.4:
            diagnosis["problems"].append({
                "name": "首个结果相关性差",
                "metric": "mrr",
                "value": mrr_val,
                "severity": "critical"
            })
            diagnosis["root_causes"].append({
                "cause": "排序质量差",
                "evidence": f"MRR={mrr_val:.2f}，用户需要翻找才能找到答案",
                "category": "ranking"
            })
            diagnosis["solutions"].append({
                "action": "大幅增加重排权重",
                "config": {
                    "retrieval.enable_rerank": True,
                    "retrieval.llm_weight": 0.9
                },
                "priority": "high",
                "expected_improvement": "MRR +25-30%"
            })

        elif mrr_val < 0.5:
            diagnosis["problems"].append({
                "name": "首个结果相关性偏低",
                "metric": "mrr",
                "value": mrr_val,
                "severity": "warning"
            })
            diagnosis["solutions"].append({
                "action": "调整重排权重",
                "config": {"retrieval.llm_weight": 0.7},
                "priority": "medium",
                "expected_improvement": "MRR +10-15%"
            })

        # 延迟诊断
        avg_latency = retrieval.get("avg_latency_ms", 0)
        if avg_latency > 3000:
            diagnosis["problems"].append({
                "name": "检索延迟过高",
                "metric": "latency",
                "value": avg_latency,
                "severity": "warning"
            })
            diagnosis["root_causes"].append({
                "cause": "检索流程耗时过长",
                "evidence": f"平均延迟 {avg_latency:.0f}ms",
                "category": "performance"
            })
            diagnosis["solutions"].append({
                "action": "优化性能",
                "config": {
                    "retrieval.top_k_retrieval": 15,
                    "retrieval.enable_multiquery": False
                },
                "priority": "medium",
                "expected_improvement": "延迟 -50%"
            })

        # 综合诊断
        if not diagnosis["problems"]:
            diagnosis["overall_status"] = "healthy"
            diagnosis["summary"] = "系统运行良好，无需优化"
        else:
            critical_count = sum(1 for p in diagnosis["problems"] if p["severity"] == "critical")
            if critical_count > 0:
                diagnosis["overall_status"] = "critical"
                diagnosis["summary"] = f"发现 {critical_count} 个严重问题，需要立即优化"
            else:
                diagnosis["overall_status"] = "warning"
                diagnosis["summary"] = f"发现 {len(diagnosis['problems'])} 个问题，建议优化"

        return diagnosis

    def generate_optimization_report(
        self,
        analysis: Dict[str, Any],
        output_path: Optional[str] = None
    ) -> str:
        """
        生成优化报告

        Args:
            analysis: 分析结果
            output_path: 输出路径

        Returns:
            报告文本
        """
        lines = [
            "=" * 60,
            "RAG系统优化报告",
            "=" * 60,
            f"生成时间: {datetime.now().isoformat()}",
            f"评估文件: {analysis.get('eval_file', 'N/A')}",
            f"问题数量: {analysis.get('questions_count', 0)}",
            ""
        ]

        # 指标分析
        metrics = analysis.get("metrics_analysis", {})
        if metrics:
            lines.append("【评估指标】")
            recall = metrics.get("recall", {})
            lines.append(f"  Recall@1:  {recall.get('recall@1', 0):.4f}  {'✓' if recall.get('recall@1', 0) >= 0.5 else '✗'}")
            lines.append(f"  Recall@5:  {recall.get('recall@5', 0):.4f}  {'✓' if recall.get('recall@5', 0) >= 0.7 else '✗'}")
            lines.append(f"  Recall@10: {recall.get('recall@10', 0):.4f}  {'✓' if recall.get('recall@10', 0) >= 0.8 else '✗'}")
            lines.append(f"  MRR:       {metrics.get('mrr', {}).get('value', 0):.4f}  {'✓' if metrics.get('mrr', {}).get('value', 0) >= 0.5 else '✗'}")
            lines.append(f"  NDCG@5:    {metrics.get('ndcg', {}).get('value', 0):.4f}  {'✓' if metrics.get('ndcg', {}).get('value', 0) >= 0.6 else '✗'}")
            lines.append("")

        # 延迟分析
        retrieval = analysis.get("retrieval_analysis", {})
        if retrieval:
            lines.append("【检索性能】")
            lines.append(f"  平均延迟: {retrieval.get('avg_latency_ms', 0):.1f}ms")
            lines.append(f"  最大延迟: {retrieval.get('max_latency_ms', 0):.1f}ms")
            lines.append(f"  慢查询数: {len(retrieval.get('slow_queries', []))}")
            lines.append("")

        # 系统化诊断
        diagnosis = self.diagnose(analysis)
        if diagnosis.get("problems"):
            lines.append("【诊断结果】")
            lines.append(f"  状态: {diagnosis['overall_status'].upper()}")
            lines.append(f"  总结: {diagnosis['summary']}")
            lines.append("")

            lines.append("  问题:")
            for p in diagnosis["problems"]:
                severity_icon = "🔴" if p["severity"] == "critical" else "🟡"
                lines.append(f"    {severity_icon} {p['name']} ({p['metric']}={p['value']:.4f})")
            lines.append("")

            lines.append("  根因分析:")
            for rc in diagnosis["root_causes"]:
                lines.append(f"    - {rc['cause']}")
                lines.append(f"      证据: {rc['evidence']}")
            lines.append("")

            lines.append("  解决方案:")
            for i, sol in enumerate(diagnosis["solutions"], 1):
                lines.append(f"    {i}. [{sol['priority'].upper()}] {sol['action']}")
                lines.append(f"       预期效果: {sol['expected_improvement']}")
                lines.append(f"       配置修改:")
                for key, value in sol["config"].items():
                    lines.append(f"         - {key}: {value}")
            lines.append("")

        # 优化建议（详细）
        suggestions = analysis.get("suggestions", [])
        if suggestions:
            lines.append("【优化建议详情】")
            for i, s in enumerate(suggestions, 1):
                lines.append(f"  {i}. [{s.priority.upper()}] {s.suggestion}")
                lines.append(f"     指标: {s.metric} (当前: {s.current_value:.4f}, 目标: {s.target_value:.4f})")
                lines.append(f"     配置修改:")
                for key, value in s.config_changes.items():
                    lines.append(f"       - {key}: {value}")
                lines.append("")

        report = "\n".join(lines)

        # 保存报告
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)

        return report


def run_optimization(eval_file: Optional[str] = None, auto_apply: bool = False):
    """运行优化流程"""
    optimizer = RAGOptimizer()

    print("分析评估结果...")
    analysis = optimizer.analyze_eval_results(eval_file)

    if "error" in analysis:
        print(f"错误: {analysis['error']}")
        return

    # 生成报告
    report = optimizer.generate_optimization_report(analysis, "data/eval_results/optimization_report.txt")
    print(report)

    # 如果有建议，询问是否应用
    suggestions = analysis.get("suggestions", [])
    if suggestions and auto_apply:
        from config.presets import get_preset
        config = get_preset(analysis.get("config", "base"))
        new_config, changes = optimizer.apply_suggestions(config, suggestions, auto_apply=True)

        if changes:
            print("\n已应用以下配置修改:")
            for change in changes:
                print(f"  - {change}")
        else:
            print("\n无需修改配置")


if __name__ == "__main__":
    import sys
    eval_file = sys.argv[1] if len(sys.argv) > 1 else None
    run_optimization(eval_file, auto_apply=False)
