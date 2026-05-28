import json
import logging
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from backend.api.deps import get_kb_manager, get_current_user

ROOT = Path(__file__).parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)
router = APIRouter()


class EvalRunRequest(BaseModel):
    kb_id: Optional[str] = None
    config_name: str = "base"
    questions: Optional[List[str]] = None   # 不传则使用内置测试集


@router.post("/run")
def run_eval(
    body: EvalRunRequest,
    mgr=Depends(get_kb_manager),
    user=Depends(get_current_user),
):
    """SSE 流式运行评估，实时推送进度"""
    from config.presets import get_preset
    from src.eval.evaluator import Evaluator
    from src.eval.eval_history import EvalHistory
    from src.pipeline import RAGPipeline
    import uuid

    async def generator():
        try:
            config = get_preset(body.config_name)

            # 如果指定了 kb_id，覆盖 index_dir
            if body.kb_id:
                import copy
                rc = copy.deepcopy(config.retrieval)
                rc.index_dir = str(mgr.fs.get_dir_path(body.kb_id, "chunked"))
                config.retrieval = rc

            pipeline = RAGPipeline(config)

            # 测试问题
            questions = body.questions or _default_questions()
            total = len(questions)
            results = []

            yield {"data": json.dumps({"stage": "start", "total": total})}

            for i, q in enumerate(questions):
                yield {"data": json.dumps({"stage": "progress", "current": i + 1,
                                           "total": total, "question": q})}
                try:
                    res = pipeline.answer_single_question(q)
                    results.append({"question": q, "answer": res.get("final_answer", "N/A"),
                                    "pages": res.get("relevant_pages", [])})
                except Exception as e:
                    results.append({"question": q, "answer": "ERROR", "error": str(e)})

            # 保存历史
            history = EvalHistory()
            eval_id = str(uuid.uuid4())
            history.save(eval_id=eval_id, config_name=body.config_name,
                         question_count=total, results=results)

            yield {"data": json.dumps({"stage": "done", "eval_id": eval_id,
                                       "total": total, "results": results})}
        except Exception as e:
            logger.error("评估失败: %s", e)
            yield {"data": json.dumps({"stage": "error", "message": str(e)})}

    return EventSourceResponse(generator())


@router.get("/history")
def eval_history(limit: int = Query(20), user=Depends(get_current_user)):
    """返回历史评估记录列表"""
    from src.eval.eval_history import EvalHistory
    history = EvalHistory()
    records = history.list_records(limit=limit)
    return records


def _default_questions() -> List[str]:
    """内置简单测试问题"""
    return [
        "这份报告的主要内容是什么？",
        "有哪些核心数据或指标？",
        "主要结论是什么？",
    ]
