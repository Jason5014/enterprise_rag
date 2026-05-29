import json
import logging
import sys
import time
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

EVAL_QUESTIONS_FILE = ROOT / "data" / "eval_questions.json"


def _load_eval_data():
    """加载 data/eval_questions.json"""
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


def _compute_recall(retrieved: List[str], relevant: List[str], k: int) -> float:
    if not relevant:
        return 0.0
    hits = len(set(retrieved[:k]) & set(relevant))
    return hits / len(relevant)


def _compute_hit(retrieved: List[str], relevant: List[str], k: int) -> float:
    if not relevant:
        return 0.0
    return 1.0 if set(retrieved[:k]) & set(relevant) else 0.0


def _compute_mrr(retrieved: List[str], relevant: List[str]) -> float:
    rel_set = set(relevant)
    for i, r in enumerate(retrieved):
        if r in rel_set:
            return 1.0 / (i + 1)
    return 0.0


def _compute_ndcg(retrieved: List[str], relevant: List[str], k: int = 5) -> float:
    rel_set = set(relevant)
    import math
    dcg = sum(1.0 / math.log2(i + 2) for i, r in enumerate(retrieved[:k]) if r in rel_set)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / ideal if ideal > 0 else 0.0


class EvalRunRequest(BaseModel):
    kb_id: Optional[str] = None
    config_name: str = "base"
    questions: Optional[List[str]] = None   # 不传则使用内置测试集
    enable_llm_eval: bool = False


@router.post("/run")
def run_eval(
    body: EvalRunRequest,
    mgr=Depends(get_kb_manager),
    user=Depends(get_current_user),
):
    """SSE 流式运行评估，实时推送进度，结束时附带完整指标"""
    from src.eval.eval_history import EvalHistory
    from src.pipeline import RAGPipeline
    from config.presets import get_preset

    async def generator():
        try:
            eval_data = _load_eval_data()
            questions = body.questions or eval_data["questions"] or _default_questions()
            ground_truth = eval_data["ground_truth"]
            question_categories = eval_data["question_categories"]
            has_gt = bool(ground_truth)
            total = len(questions)

            yield {"data": json.dumps({"stage": "start", "total": total, "has_ground_truth": has_gt})}

            # 获取 pipeline
            if body.kb_id:
                kb = mgr.get_kb(body.kb_id)
                if kb is None:
                    yield {"data": json.dumps({"stage": "error", "message": "知识库不存在"})}
                    return
                pipeline = mgr.get_pipeline(body.kb_id)
            else:
                config = get_preset(body.config_name)
                pipeline = RAGPipeline(config)

            # 指标累计
            metric_lists = {k: [] for k in ["recall@1", "recall@3", "recall@5", "hit@1", "hit@3", "hit@5", "mrr", "ndcg@5"]}
            results = []
            latencies = []

            for i, q in enumerate(questions):
                yield {"data": json.dumps({"stage": "progress", "current": i + 1, "total": total, "question": q})}
                cat = question_categories.get(q, "")
                start = time.time()
                try:
                    res = pipeline.answer_single_question(q)
                    elapsed = (time.time() - start) * 1000
                    latencies.append(elapsed)
                    answer = res.get("final_answer", "N/A")
                    pages = res.get("relevant_pages", [])

                    # 从 pipeline 获取最后的检索结果（用于指标计算）
                    retrieval_log = pipeline.get_last_retrieval_log() if hasattr(pipeline, 'get_last_retrieval_log') else {}
                    retrieved_ids = []
                    if retrieval_log:
                        final_results = retrieval_log.get("final_results", [])
                        retrieved_ids = [r.get("chunk_id", "") for r in final_results[:10]]

                    q_result = {
                        "question": q, "answer": answer, "pages": pages,
                        "category": cat, "latency_ms": round(elapsed, 1),
                        "retrieved_ids": retrieved_ids,
                    }

                    if has_gt and q in ground_truth:
                        relevant = ground_truth[q].get("relevant_chunks", [])
                        if relevant:
                            for k_val in [1, 3, 5]:
                                metric_lists[f"recall@{k_val}"].append(_compute_recall(retrieved_ids, relevant, k_val))
                                metric_lists[f"hit@{k_val}"].append(_compute_hit(retrieved_ids, relevant, k_val))
                            metric_lists["mrr"].append(_compute_mrr(retrieved_ids, relevant))
                            metric_lists["ndcg@5"].append(_compute_ndcg(retrieved_ids, relevant, 5))
                            q_result["relevant_chunks"] = relevant
                            q_result["is_hit"] = bool(set(retrieved_ids[:5]) & set(relevant))

                    results.append(q_result)

                except Exception as e:
                    elapsed = (time.time() - start) * 1000
                    latencies.append(elapsed)
                    results.append({"question": q, "answer": "ERROR", "error": str(e),
                                    "latency_ms": round(elapsed, 1)})

            # 汇总指标
            avg_metrics = {k: (sum(v) / len(v) if v else 0.0) for k, v in metric_lists.items()}
            avg_latency = sum(latencies) / len(latencies) if latencies else 0
            avg_metrics["avg_latency_ms"] = round(avg_latency, 1)

            # 综合得分（4 个核心指标均值 * 100）
            core_keys = ["hit@5", "recall@5", "mrr", "ndcg@5"]
            core_vals = [avg_metrics[k] for k in core_keys if avg_metrics.get(k)]
            composite_score = round(sum(core_vals) / len(core_vals) * 100, 1) if core_vals else 0.0

            # 保存历史
            history = EvalHistory()
            eval_id = history.save(
                config_name=body.config_name,
                question_count=total,
                metrics=avg_metrics,
                composite_score=composite_score,
                query_results=results,
            )

            yield {"data": json.dumps({
                "stage": "done",
                "eval_id": eval_id,
                "total": total,
                "results": results,
                "metrics": avg_metrics,
                "avg_latency_ms": round(avg_latency, 1),
                "has_ground_truth": has_gt,
            })}

        except Exception as e:
            logger.error("评估失败: %s", e)
            yield {"data": json.dumps({"stage": "error", "message": str(e)})}

    return EventSourceResponse(generator())


@router.get("/history")
def eval_history(limit: int = Query(20), user=Depends(get_current_user)):
    """返回历史评估记录列表（包含指标）"""
    from src.eval.eval_history import EvalHistory
    history = EvalHistory()
    records = history.get_history(limit=limit)
    return list(reversed(records))   # 最新的在前


@router.get("/questions")
def list_questions(user=Depends(get_current_user)):
    """返回当前评估问题集信息"""
    data = _load_eval_data()
    return {
        "total": len(data["questions"]),
        "has_ground_truth": bool(data["ground_truth"]),
        "categories": data["categories"],
        "questions": data["questions"][:50],   # 最多返回50条预览
    }


def _default_questions() -> List[str]:
    return [
        "中芯国际2024年营收是多少？",
        "中芯国际的主要客户有哪些？",
        "中芯国际的研发投入占营收比例是多少？",
    ]
