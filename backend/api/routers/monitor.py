import json
import logging
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.api.deps import get_current_user

ROOT = Path(__file__).parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_collector():
    from src.feedback_collector import FeedbackCollector
    return FeedbackCollector()


@router.get("/stats")
def stats(user=Depends(get_current_user)):
    """问答概览统计"""
    collector = _get_collector()
    all_fb = collector._feedback_cache
    total = len(all_fb)
    good = sum(1 for f in all_fb if f.get("user_feedback", {}).get("rating") == "good"
               or f.get("feedback") == "good")
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
    user=Depends(get_current_user),
):
    """Bad Case 列表，支持关键词筛选"""
    collector = _get_collector()
    all_fb = collector._feedback_cache
    bad = [
        f for f in all_fb
        if f.get("user_feedback", {}).get("rating") == "bad"
        or f.get("feedback") == "bad"
    ]
    if keyword:
        bad = [f for f in bad if keyword in f.get("query", "") or keyword in f.get("answer", "")]
    total = len(bad)
    page = bad[offset: offset + limit]
    return {"total": total, "items": page}


@router.post("/export")
def export_bad_cases(user=Depends(get_current_user)):
    """导出所有 Bad Case 为 JSONL 流"""
    collector = _get_collector()
    all_fb = collector._feedback_cache
    bad = [
        f for f in all_fb
        if f.get("user_feedback", {}).get("rating") == "bad"
        or f.get("feedback") == "bad"
    ]
    lines = "\n".join(json.dumps(f, ensure_ascii=False) for f in bad)
    return StreamingResponse(
        iter([lines]),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=bad_cases.jsonl"},
    )
