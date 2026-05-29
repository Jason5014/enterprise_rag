import copy
import json
import logging
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from backend.api.deps import get_kb_manager, get_current_user
from backend.api.schemas.qa import QARequest, QAResponse, FeedbackRequest

logger = logging.getLogger(__name__)
router = APIRouter()

_DEFAULT_KB_ID = "__default__"


def _build_pipeline(config_name: str, overrides: Optional[Dict[str, Any]] = None):
    """用给定预设 + 覆盖参数构建 RAGPipeline"""
    import sys
    from pathlib import Path
    ROOT = Path(__file__).parent.parent.parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from config.presets import get_preset
    from config.retrieval_config import RetrievalConfig
    from config.settings import ConfigBundle
    from config.answer_config import AnswerConfig
    from src.pipeline import RAGPipeline

    preset = get_preset(config_name)

    if overrides:
        retrieval = copy.deepcopy(preset.retrieval) if preset.retrieval else RetrievalConfig()
        for k, v in overrides.items():
            if hasattr(retrieval, k):
                setattr(retrieval, k, v)
        bundle = ConfigBundle(
            retrieval=retrieval,
            answer=preset.answer or AnswerConfig(),
            pdf=preset.pdf,
            embedding=preset.embedding,
        )
        return RAGPipeline(bundle)

    return RAGPipeline(preset)


def _get_pipeline(kb_id: Optional[str], mgr, config_name: str = "base",
                  overrides: Optional[Dict[str, Any]] = None):
    """获取 pipeline；有 overrides 时总是新建"""
    if overrides:
        return _build_pipeline(config_name, overrides)

    if not kb_id or kb_id == _DEFAULT_KB_ID:
        return _build_pipeline(config_name, None)

    kb = mgr.get_kb(kb_id)
    if kb is None:
        raise HTTPException(404, "知识库不存在")
    return mgr.get_pipeline(kb_id)


@router.post("/ask", response_model=QAResponse)
def ask(body: QARequest, mgr=Depends(get_kb_manager), user=Depends(get_current_user)):
    """同步问答"""
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
    overrides: Optional[str] = Query(None, description="JSON 编码的参数覆盖"),
    token: Optional[str] = Query(None, description="JWT token"),
    mgr=Depends(get_kb_manager),
    user=Depends(get_current_user),
):
    """SSE 流式问答"""
    overrides_dict: Optional[Dict[str, Any]] = None
    if overrides:
        try:
            overrides_dict = json.loads(overrides)
        except Exception:
            pass

    pipeline = _get_pipeline(kb_id, mgr, config_name, overrides_dict)

    async def generator():
        try:
            for chunk in pipeline.stream_answer(q):
                if isinstance(chunk, dict) and chunk.get("__meta__"):
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
    """提交问答反馈（👍/👎）"""
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
    """清空对话历史"""
    if kb_id and kb_id != _DEFAULT_KB_ID:
        try:
            pipeline = mgr.get_pipeline(kb_id)
            pipeline.reset_history()
        except Exception:
            pass
    return {"status": "ok"}
