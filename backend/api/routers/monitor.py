import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from backend.api.deps import get_current_user

ROOT = Path(__file__).parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)
router = APIRouter()

EVAL_QUESTIONS_FILE = ROOT / "data" / "eval_questions.json"


def _get_collector():
    from src.eval.feedback_collector import FeedbackCollector
    return FeedbackCollector()


def _is_bad(f: dict) -> bool:
    return (f.get("user_feedback", {}).get("rating") == "bad"
            or f.get("feedback") == "bad"
            or not f.get("user_feedback", {}).get("helpful", True))


@router.get("/stats")
def stats(user=Depends(get_current_user)):
    """问答概览统计"""
    collector = _get_collector()
    all_fb = collector._feedback_cache
    total = len(all_fb)
    good = sum(1 for f in all_fb if not _is_bad(f))
    bad = total - good
    return {
        "total": total,
        "good": good,
        "bad": bad,
        "good_rate": round(good / total * 100, 1) if total else 0,
    }


@router.get("/bad-cases")
def bad_cases(
    limit: int = Query(50),
    offset: int = Query(0),
    keyword: Optional[str] = Query(None),
    error_type: Optional[str] = Query(None),
    config_name: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    """Bad Case 列表，支持关键词/错误类型/配置筛选"""
    collector = _get_collector()
    bad = [f for f in collector._feedback_cache if _is_bad(f)]

    if keyword:
        bad = [f for f in bad if keyword in f.get("query", "") or keyword in str(f.get("answer", ""))]
    if error_type:
        bad = [f for f in bad if f.get("user_feedback", {}).get("error_type") == error_type]
    if config_name:
        bad = [f for f in bad if f.get("config_name") == config_name]

    total = len(bad)
    page = bad[offset: offset + limit]
    return {"total": total, "items": page}


@router.get("/error-analysis")
def error_analysis(user=Depends(get_current_user)):
    """错误模式聚合分析：按错误类型统计，附带优化建议"""
    collector = _get_collector()
    bad = [f for f in collector._feedback_cache if _is_bad(f)]

    error_counts: dict = defaultdict(int)
    error_queries: dict = defaultdict(list)
    for f in bad:
        etype = f.get("user_feedback", {}).get("error_type") or "unclassified"
        error_counts[etype] += 1
        error_queries[etype].append(f.get("query", "")[:60])

    # 各阶段 Bad Case 分布
    stage_map = {
        "hallucination": "generate",
        "irrelevant": "retrieval",
        "incomplete": "retrieval+generate",
        "factual_error": "retrieval+generate",
        "outdated": "index",
    }
    stage_counts: dict = defaultdict(int)
    for f in bad:
        etype = f.get("user_feedback", {}).get("error_type", "")
        stage = stage_map.get(etype, "unknown")
        stage_counts[stage] += 1

    # 按配置统计好评率
    by_config: dict = defaultdict(lambda: {"total": 0, "helpful": 0})
    for f in collector._feedback_cache:
        cfg = f.get("config_name", "unknown")
        by_config[cfg]["total"] += 1
        if not _is_bad(f):
            by_config[cfg]["helpful"] += 1

    return {
        "total_bad": len(bad),
        "error_types": dict(error_counts),
        "error_queries": {k: v[:3] for k, v in error_queries.items()},
        "stage_distribution": dict(stage_counts),
        "by_config": {
            k: {
                "total": v["total"],
                "helpful": v["helpful"],
                "good_rate": round(v["helpful"] / v["total"] * 100, 1) if v["total"] else 0
            }
            for k, v in by_config.items()
        },
    }


@router.post("/export")
def export_bad_cases(user=Depends(get_current_user)):
    """导出所有 Bad Case 为 JSONL"""
    collector = _get_collector()
    bad = [f for f in collector._feedback_cache if _is_bad(f)]
    lines = "\n".join(json.dumps(f, ensure_ascii=False) for f in bad)
    return StreamingResponse(
        iter([lines]),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=bad_cases.jsonl"},
    )


@router.post("/add-to-eval")
def add_to_eval(user=Depends(get_current_user)):
    """将有纠正答案的 Bad Case 加入 eval_questions.json"""
    collector = _get_collector()
    bad = [f for f in collector._feedback_cache if _is_bad(f)]

    eval_path = EVAL_QUESTIONS_FILE
    if eval_path.exists():
        eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
    else:
        eval_data = {"questions": [], "ground_truth": {}}

    added = 0
    for f in bad:
        q = f.get("query", "")
        ub = f.get("user_feedback", {})
        correct = ub.get("correct_answer", "")
        if q and correct and q not in eval_data.get("questions", []):
            eval_data.setdefault("questions", []).append(q)
            eval_data.setdefault("ground_truth", {})[q] = {"answer": correct}
            added += 1

    if added > 0:
        eval_path.parent.mkdir(parents=True, exist_ok=True)
        eval_path.write_text(json.dumps(eval_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"added": added, "message": f"已将 {added} 条 Bad Case 加入评测集"}
