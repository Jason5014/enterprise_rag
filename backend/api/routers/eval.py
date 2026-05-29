import copy
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from backend.api.deps import get_kb_manager, get_current_user

ROOT = Path(__file__).parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)
router = APIRouter()

EVAL_QUESTIONS_FILE = ROOT / "data" / "eval_questions.json"


def _load_eval_data():
    if not EVAL_QUESTIONS_FILE.exists():
        return {"questions": [], "ground_truth": {}, "question_categories": {}, "categories": {}}
    try:
        data = json.loads(EVAL_QUESTIONS_FILE.read_text(encoding="utf-8"))
        return {
            "questions": data.get("questions", []),
            "ground_truth": data.get("ground_truth", {}),
            "question_categories": data.get("question_categories", {}),
            "categories": data.get("categories", {}),
        }
    except Exception:
        return {"questions": [], "ground_truth": {}, "question_categories": {}, "categories": {}}


def _compute_recall(retrieved, relevant, k):
    if not relevant: return 0.0
    return len(set(retrieved[:k]) & set(relevant)) / len(relevant)


def _compute_hit(retrieved, relevant, k):
    if not relevant: return 0.0
    return 1.0 if set(retrieved[:k]) & set(relevant) else 0.0


def _compute_mrr(retrieved, relevant):
    rel_set = set(relevant)
    for i, r in enumerate(retrieved):
        if r in rel_set:
            return 1.0 / (i + 1)
    return 0.0


def _compute_ndcg(retrieved, relevant, k=5):
    import math
    rel_set = set(relevant)
    dcg = sum(1.0 / math.log2(i + 2) for i, r in enumerate(retrieved[:k]) if r in rel_set)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / ideal if ideal > 0 else 0.0


def _build_pipeline(config_name: str, overrides: Optional[Dict[str, Any]] = None):
    """构建 RAGPipeline，可选参数覆盖"""
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


class EvalRunRequest(BaseModel):
    kb_id: Optional[str] = None
    config_name: str = "base"
    display_name: Optional[str] = None       # 显示名称（自定义变体时用）
    questions: Optional[List[str]] = None
    category_filter: Optional[str] = None    # 按场景分类筛选
    enable_llm_eval: bool = False
    overrides: Optional[Dict[str, Any]] = None   # 运行时参数覆盖


async def _run_eval_generator(body: EvalRunRequest, mgr):
    """核心评估逻辑，返回 async generator"""
    try:
        eval_data = _load_eval_data()
        all_questions = body.questions or eval_data["questions"] or _default_questions()

        # 场景筛选
        if body.category_filter and body.category_filter != "全部":
            qcat = eval_data["question_categories"]
            all_questions = [q for q in all_questions if qcat.get(q) == body.category_filter]

        ground_truth = eval_data["ground_truth"]
        question_categories = eval_data["question_categories"]
        has_gt = bool(ground_truth)
        total = len(all_questions)
        display = body.display_name or body.config_name

        yield {"data": json.dumps({
            "stage": "start",
            "total": total,
            "has_ground_truth": has_gt,
            "config_name": display,
        })}

        # 构建 pipeline
        if body.kb_id:
            kb_obj = mgr.get_kb(body.kb_id)
            if kb_obj is None:
                yield {"data": json.dumps({"stage": "error", "message": "知识库不存在"})}
                return
            pipeline = mgr.get_pipeline(body.kb_id)
        else:
            pipeline = _build_pipeline(body.config_name, body.overrides)

        metric_lists = {k: [] for k in [
            "recall@1", "recall@3", "recall@5",
            "hit@1", "hit@3", "hit@5",
            "mrr", "ndcg@5",
        ]}
        results = []
        latencies = []
        cat_metric_lists: Dict[str, Dict[str, List[float]]] = {}

        for i, q in enumerate(all_questions):
            yield {"data": json.dumps({
                "stage": "progress",
                "current": i + 1,
                "total": total,
                "question": q,
                "config_name": display,
            })}
            cat = question_categories.get(q, "")
            if cat not in cat_metric_lists:
                cat_metric_lists[cat] = {k: [] for k in metric_lists}

            start = time.time()
            try:
                res = pipeline.answer_single_question(q)
                elapsed = (time.time() - start) * 1000
                latencies.append(elapsed)
                answer = res.get("final_answer", "N/A")
                pages = res.get("relevant_pages", [])

                retrieval_log = getattr(pipeline, "get_last_retrieval_log", lambda: {})()
                retrieved_ids = []
                if retrieval_log:
                    retrieved_ids = [r.get("chunk_id", "") for r in retrieval_log.get("final_results", [])[:10]]

                q_result = {
                    "question": q, "answer": answer, "pages": pages,
                    "category": cat, "latency_ms": round(elapsed, 1),
                    "retrieved_ids": retrieved_ids,
                }

                if has_gt and q in ground_truth:
                    relevant = ground_truth[q].get("relevant_chunks", [])
                    if relevant:
                        for k_val in [1, 3, 5]:
                            r_val = _compute_recall(retrieved_ids, relevant, k_val)
                            h_val = _compute_hit(retrieved_ids, relevant, k_val)
                            metric_lists[f"recall@{k_val}"].append(r_val)
                            metric_lists[f"hit@{k_val}"].append(h_val)
                            cat_metric_lists[cat][f"recall@{k_val}"].append(r_val)
                            cat_metric_lists[cat][f"hit@{k_val}"].append(h_val)
                        mrr = _compute_mrr(retrieved_ids, relevant)
                        ndcg = _compute_ndcg(retrieved_ids, relevant, 5)
                        metric_lists["mrr"].append(mrr)
                        metric_lists["ndcg@5"].append(ndcg)
                        cat_metric_lists[cat]["mrr"].append(mrr)
                        cat_metric_lists[cat]["ndcg@5"].append(ndcg)
                        q_result["relevant_chunks"] = relevant
                        q_result["is_hit"] = bool(set(retrieved_ids[:5]) & set(relevant))

                results.append(q_result)

            except Exception as e:
                elapsed = (time.time() - start) * 1000
                latencies.append(elapsed)
                results.append({"question": q, "answer": "ERROR", "error": str(e),
                                 "latency_ms": round(elapsed, 1)})

        avg_metrics = {k: (sum(v) / len(v) if v else 0.0) for k, v in metric_lists.items()}
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        avg_metrics["avg_latency_ms"] = round(avg_latency, 1)

        # 分类指标
        category_metrics = {}
        for cat, m in cat_metric_lists.items():
            category_metrics[cat] = {k: (sum(v) / len(v) if v else 0.0) for k, v in m.items()}
            category_metrics[cat]["count"] = len([q for q in all_questions if question_categories.get(q) == cat])

        # 综合分
        core_vals = [avg_metrics[k] for k in ["hit@5", "recall@5", "mrr", "ndcg@5"] if avg_metrics.get(k)]
        composite_score = round(sum(core_vals) / len(core_vals) * 100, 1) if core_vals else 0.0

        # 保存历史
        from src.eval.eval_history import EvalHistory
        history = EvalHistory()
        eval_id = history.save(
            config_name=body.config_name,
            question_count=total,
            metrics=avg_metrics,
            composite_score=composite_score,
            category_metrics=category_metrics,
            query_results=results,
        )

        yield {"data": json.dumps({
            "stage": "done",
            "eval_id": eval_id,
            "config_name": display,
            "total": total,
            "results": results,
            "metrics": avg_metrics,
            "category_metrics": category_metrics,
            "avg_latency_ms": round(avg_latency, 1),
            "composite_score": composite_score,
            "has_ground_truth": has_gt,
        })}

    except Exception as e:
        logger.error("评估失败: %s", e)
        yield {"data": json.dumps({"stage": "error", "message": str(e)})}


@router.post("/run")
def run_eval(
    body: EvalRunRequest,
    mgr=Depends(get_kb_manager),
    user=Depends(get_current_user),
):
    """SSE 流式运行评估（单配置）"""
    async def generator():
        async for event in _run_eval_generator(body, mgr):
            yield event

    return EventSourceResponse(generator())


@router.get("/history")
def eval_history(limit: int = Query(20), user=Depends(get_current_user)):
    from src.eval.eval_history import EvalHistory
    history = EvalHistory()
    records = history.get_history(limit=limit)
    return list(reversed(records))


@router.get("/questions")
def list_questions(user=Depends(get_current_user)):
    data = _load_eval_data()
    return {
        "total": len(data["questions"]),
        "has_ground_truth": bool(data["ground_truth"]),
        "categories": data["categories"],
        "question_categories": data["question_categories"],
        "questions": data["questions"][:50],
    }


def _default_questions() -> List[str]:
    return [
        "中芯国际2024年营收是多少？",
        "中芯国际的主要客户有哪些？",
        "中芯国际的研发投入占营收比例是多少？",
    ]
