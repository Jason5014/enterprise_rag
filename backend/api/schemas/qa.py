from pydantic import BaseModel
from typing import Optional, List


class QARequest(BaseModel):
    query: str
    kb_id: Optional[str] = None
    config_name: Optional[str] = None


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
    feedback: str   # "good" / "bad"
    comment: Optional[str] = None
    kb_id: Optional[str] = None
