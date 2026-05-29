import json
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from backend.api.deps import get_kb_manager, get_current_user
from backend.api.schemas.qa import QARequest, QAResponse, FeedbackRequest

logger = logging.getLogger(__name__)
router = APIRouter()

_DEFAULT_KB_ID = "__default__"


def _get_pipeline(kb_id: Optional[str], mgr, config_name: str = "base"):
    """获取 pipeline；kb_id 为空时用内置默认索引，config_name 控制预设配置。"""
    import sys
    from pathlib import Path
    ROOT = Path(__file__).parent.parent.parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from config.presets import get_preset

    if not kb_id or kb_id == _DEFAULT_KB_ID:
        from src.pipeline import RAGPipeline
        config = get_preset(config_name)
        return RAGPipeline(config)

    kb = mgr.get_kb(kb_id)
    if kb is None:
        raise HTTPException(404, "知识库不存在")
    # 已缓存的 pipeline 使用 kb 自己的 config_name；但若前端显式传了 config_name 则覆盖
    import copy
    from src.pipeline import RAGPipeline
    config = get_preset(kb.config_name if kb.config_name else config_name)
    pipeline = mgr.get_pipeline(kb_id)
    return pipeline


@router.post("/ask", response_model=QAResponse)
def ask(body: QARequest, mgr=Depends(get_kb_manager), user=Depends(get_current_user)):
    """同步问答（等待完整答案后返回）"""
    pipeline = _get_pipeline(body.kb_id, mgr, body.config_name or "base")
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
    kb_id: Optional[str] = Query(None),
    config_name: str = Query("base", description="预设配置名"),
    token: Optional[str] = Query(None, description="JWT token（EventSource 通过此参数传递）"),
    mgr=Depends(get_kb_manager),
    user=Depends(get_current_user),
):
    """SSE 流式问答 — 逐 token 推送，最后推送 [META] 和 [DONE]"""
    pipeline = _get_pipeline(kb_id, mgr, config_name)

    async def generator():
        try:
            for chunk in pipeline.stream_answer(q):
                if isinstance(chunk, dict) and chunk.get("__meta__"):
                    # 末尾元数据事件：页码、chunk 数
                    yield {"event": "meta", "data": json.dumps(chunk)}
                else:
                    yield {"data": str(chunk)}
            yield {"data": "[DONE]"}
        except Exception as e:
            logger.error("流式问答失败: %s", e)
            yield {"data": json.dumps({"error": str(e)})}

    return EventSourceResponse(generator())


@router.post("/feedback")
def feedback(body: FeedbackRequest, user=Depends(get_current_user)):
    """提交问答反馈（👍/👎），支持详细错误类型和纠正答案"""
    try:
        import sys
        from pathlib import Path
        ROOT = Path(__file__).parent.parent.parent.parent
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from src.eval.feedback_collector import FeedbackCollector
        collector = FeedbackCollector()
        collector.collect(
            query=body.query,
            answer=body.answer,
            helpful=(body.feedback == "good"),
            error_type=body.error_type,
            correct_answer=body.correct_answer,
            relevant_pages=body.pages or [],
            config_name=body.config_name or "base",
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
