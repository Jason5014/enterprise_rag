from pydantic import BaseModel
from typing import Optional, List


class QARequest(BaseModel):
    query: str
    kb_id: Optional[str] = None
    config_name: Optional[str] = "base"


class QAResponse(BaseModel):
    query: str
    final_answer: str
    step_by_step_analysis: str
    reasoning_summary: str
    relevant_pages: List[int]
    used_parent_chunks: List[str]


class FeedbackRequest(BaseModel):
    query: str
    answer: str
    feedback: str            # "good" / "bad"
    comment: Optional[str] = None
    kb_id: Optional[str] = None
    config_name: Optional[str] = "base"
    # 详细差评字段
    error_type: Optional[str] = None      # hallucination / irrelevant / incomplete / factual_error / outdated / other
    correct_answer: Optional[str] = None  # 用户纠正的正确答案
    pages: Optional[List[int]] = None     # 引用页码（从前端传回）
