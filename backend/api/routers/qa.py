import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from backend.api.deps import get_kb_manager, get_current_user
from backend.api.schemas.qa import QARequest, QAResponse, FeedbackRequest

logger = logging.getLogger(__name__)
router = APIRouter()

# 内置默认知识库（data/chunked），kb_id=None 时使用
_DEFAULT_KB_ID = "__default__"


def _get_pipeline(kb_id: Optional[str], mgr):
    """获取指定知识库的 pipeline；kb_id 为空时使用内置默认索引"""
    if not kb_id or kb_id == _DEFAULT_KB_ID:
        # 使用原有 data/chunked 目录的内置知识库
        import sys
        from pathlib import Path
        ROOT = Path(__file__).parent.parent.parent.parent
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from config.presets import get_preset
        from src.pipeline import RAGPipeline
        config = get_preset("base")
        return RAGPipeline(config)
    kb = mgr.get_kb(kb_id)
    if kb is None:
        raise HTTPException(404, "知识库不存在")
    return mgr.get_pipeline(kb_id)


@router.post("/ask", response_model=QAResponse)
def ask(body: QARequest, mgr=Depends(get_kb_manager), user=Depends(get_current_user)):
    """同步问答（等待完整答案后返回）"""
    pipeline = _get_pipeline(body.kb_id, mgr)
    result = pipeline.answer_single_question(body.query)
    return QAResponse(
        query=body.query,
        final_answer=result.get("final_answer", "N/A"),
        step_by_step_analysis=result.get("step_by_step_analysis", ""),
        reasoning_summary=result.get("reasoning_summary", ""),
        relevant_pages=result.get("relevant_pages", []),
        used_parent_chunks=result.get("used_parent_chunks", []),
    )


@router.get("/stream")
def stream_ask(
    q: str = Query(..., description="用户问题"),
    kb_id: Optional[str] = Query(None, description="知识库 ID，不传使用默认知识库"),
    token: Optional[str] = Query(None, description="JWT token（EventSource 无法设 Header，通过此参数传递）"),
    mgr=Depends(get_kb_manager),
    user=Depends(get_current_user),
):
    """SSE 流式问答 — 逐 token 推送，最后发送 [DONE]"""
    pipeline = _get_pipeline(kb_id, mgr)

    async def generator():
        try:
            for token in pipeline.stream_answer(q):
                yield {"data": token}
            yield {"data": "[DONE]"}
        except Exception as e:
            logger.error("流式问答失败: %s", e)
            yield {"data": json.dumps({"error": str(e)})}

    return EventSourceResponse(generator())


@router.post("/feedback")
def feedback(body: FeedbackRequest, user=Depends(get_current_user)):
    """提交问答反馈（👍/👎），写入 feedback_collector"""
    try:
        import sys
        from pathlib import Path
        ROOT = Path(__file__).parent.parent.parent.parent
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from src.eval.feedback_collector import FeedbackCollector
        collector = FeedbackCollector()
        collector.add(
            query=body.query,
            answer=body.answer,
            feedback=body.feedback,
            comment=body.comment or "",
        )
    except Exception as e:
        logger.warning("反馈记录失败: %s", e)
    return {"status": "ok"}


@router.delete("/history")
def clear_history(
    kb_id: Optional[str] = Query(None),
    mgr=Depends(get_kb_manager),
    user=Depends(get_current_user),
):
    """清空某知识库的对话历史（如已缓存）"""
    if kb_id and kb_id != _DEFAULT_KB_ID:
        try:
            pipeline = mgr.get_pipeline(kb_id)
            pipeline.reset_history()
        except Exception:
            pass
    return {"status": "ok"}
