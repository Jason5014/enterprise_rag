#!/usr/bin/env python3
"""LLM-as-Judge 评估脚本 - 支持按场景分类统计"""
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import get_preset
from config.settings import ConfigBundle
from config.eval_config import EvalConfig
from src.pipeline import RAGPipeline
from src.evaluator import LLMJudgeEvaluator


def load_questions(questions_path: str = "data/eval_questions.json"):
    """加载评估问题（含场景分类）"""
    path = Path(questions_path)
    if not path.exists():
        print(f"问题文件不存在: {questions_path}")
        print("使用默认问题...")
        return [
            {
                "question": "中芯国际2024年营收是多少？",
                "expected_answer": "523.48亿元",
                "context": "中芯国际2024年年度报告显示，公司实现营业收入523.48亿元。",
                "category": "FINANCIAL"
            },
            {
                "question": "公司的研发投入是多少？",
                "expected_answer": "72.8亿元",
                "context": "2024年公司研发投入72.8亿元，占营收比例13.9%。",
                "category": "FINANCIAL"
            }
        ]

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    questions = data.get("questions", [])
    ground_truth = data.get("ground_truth", {})
    question_categories = data.get("question_categories", {})
    categories_meta = data.get("categories", {})

    # 转换格式
    result = []
    for q in questions:
        item = {
            "question": q,
            "category": question_categories.get(q, "UNKNOWN")
        }
        if q in ground_truth:
            gt = ground_truth[q]
            if isinstance(gt, dict):
                item["expected_answer"] = gt.get("answer", "")
                item["context"] = gt.get("context", "")
            elif isinstance(gt, list):
                item["expected_answer"] = gt[0] if gt else ""
        result.append(item)

    return result, categories_meta


def run_evaluation(config_name: str = "full", questions_path: str = "data/eval_questions.json"):
    """运行LLM评估（含按场景分类统计）"""
    print("=" * 60)
    print("LLM-as-Judge 评估")
    print("=" * 60)

    # 加载配置
    preset = get_preset(config_name)
    print(f"使用配置: {config_name}")

    # 创建RAG管道
    pipeline = RAGPipeline(preset)

    # 创建LLM评估器
    eval_config = preset.eval_config if preset.eval_config else EvalConfig()
    judge = LLMJudgeEvaluator(config=eval_config)

    # 加载问题
    questions, categories_meta = load_questions(questions_path)
    print(f"加载问题: {len(questions)} 个")

    # 显示分类信息
    if categories_meta:
        print("\n场景分类:")
        for cat, desc in categories_meta.items():
            count = sum(1 for q in questions if q.get("category") == cat)
            print(f"  {cat}: {desc} ({count}题)")

    # 评估结果
    results = []

    # 按场景分类收集分数
    category_scores = defaultdict(lambda: {
        "faithfulness": [], "relevance": [], "completeness": []
    })
    # 全局分数
    all_scores = {"faithfulness": [], "relevance": [], "completeness": []}

    print("\n开始评估...")
    print("-" * 60)

    for i, q in enumerate(questions):
        question = q["question"]
        expected = q.get("expected_answer", "")
        context = q.get("context", "")
        category = q.get("category", "UNKNOWN")

        print(f"\n[{i+1}/{len(questions)}] [{category}] {question[:50]}...")

        # 获取RAG答案
        rag_result = pipeline.answer_single_question(question, return_retrieval_details=True)
        answer = rag_result.get("final_answer", "N/A")

        # 如果没有提供上下文，使用检索到的上下文
        if not context:
            retrieval_details = rag_result.get("retrieval_details", {})
            context = "\n".join([
                ctx.get("text", "")
                for ctx in retrieval_details.get("retrieval_results", [])
            ])

        # 评估忠实度
        if context and answer != "N/A":
            faith = judge.evaluate_faithfulness(question, answer, context)
            all_scores["faithfulness"].append(faith["score"])
            category_scores[category]["faithfulness"].append(faith["score"])
            print(f"  忠实度: {faith['score']:.2f} - {faith['reason'][:50]}")
        else:
            faith = {"score": 0, "reason": "无上下文"}
            print(f"  忠实度: 跳过（无上下文）")

        # 评估相关性
        relevance = judge.evaluate_relevance(question, answer)
        all_scores["relevance"].append(relevance["score"])
        category_scores[category]["relevance"].append(relevance["score"])
        print(f"  相关性: {relevance['score']:.2f} - {relevance['reason'][:50]}")

        # 评估完整性
        if expected:
            completeness = judge.evaluate_completeness(question, answer, expected)
            all_scores["completeness"].append(completeness["score"])
            category_scores[category]["completeness"].append(completeness["score"])
            print(f"  完整性: {completeness['score']:.2f} - {completeness['reason'][:50]}")
        else:
            completeness = {"score": 0, "reason": "无参考答案"}
            print(f"  完整性: 跳过（无参考答案）")

        # 保存详细结果
        results.append({
            "question": question,
            "category": category,
            "answer": answer,
            "expected": expected,
            "faithfulness": faith,
            "relevance": relevance,
            "completeness": completeness
        })

    # === 汇总结果 ===
    print("\n" + "=" * 60)
    print("评估结果汇总")
    print("=" * 60)

    # 全局平均
    avg_faith = sum(all_scores["faithfulness"]) / len(all_scores["faithfulness"]) if all_scores["faithfulness"] else 0
    avg_relev = sum(all_scores["relevance"]) / len(all_scores["relevance"]) if all_scores["relevance"] else 0
    avg_compl = sum(all_scores["completeness"]) / len(all_scores["completeness"]) if all_scores["completeness"] else 0

    print(f"\n【全局平均】")
    print(f"  忠实度 (Faithfulness): {avg_faith:.4f}  {'✓' if avg_faith >= 0.7 else '✗'}")
    print(f"  相关性 (Relevance):    {avg_relev:.4f}  {'✓' if avg_relev >= 0.7 else '✗'}")
    print(f"  完整性 (Completeness): {avg_compl:.4f}  {'✓' if avg_compl >= 0.7 else '✗'}")

    # 按场景分类统计
    print(f"\n【按场景分类】")
    category_results = {}
    for cat in sorted(category_scores.keys()):
        scores = category_scores[cat]
        cat_faith = sum(scores["faithfulness"]) / len(scores["faithfulness"]) if scores["faithfulness"] else 0
        cat_relev = sum(scores["relevance"]) / len(scores["relevance"]) if scores["relevance"] else 0
        cat_compl = sum(scores["completeness"]) / len(scores["completeness"]) if scores["completeness"] else 0
        count = len(scores["relevance"])  # relevance 每题都有

        cat_desc = categories_meta.get(cat, "")
        print(f"\n  [{cat}] {cat_desc} ({count}题)")
        print(f"    忠实度: {cat_faith:.4f}  {'✓' if cat_faith >= 0.7 else '✗'}")
        print(f"    相关性: {cat_relev:.4f}  {'✓' if cat_relev >= 0.7 else '✗'}")
        print(f"    完整性: {cat_compl:.4f}  {'✓' if cat_compl >= 0.7 else '✗'}")

        category_results[cat] = {
            "count": count,
            "faithfulness": round(cat_faith, 4),
            "relevance": round(cat_relev, 4),
            "completeness": round(cat_compl, 4)
        }

    # 保存报告
    output_dir = Path(eval_config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"llm_judge_{config_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    report = {
        "config": config_name,
        "timestamp": datetime.now().isoformat(),
        "questions_count": len(questions),
        "metrics": {
            "faithfulness": round(avg_faith, 4),
            "relevance": round(avg_relev, 4),
            "completeness": round(avg_compl, 4)
        },
        "category_metrics": category_results,
        "details": results
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n详细报告已保存: {output_file}")

    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LLM-as-Judge 评估")
    parser.add_argument("--config", "-c", default="full", help="配置名称")
    parser.add_argument("--questions", "-q", default="data/eval_questions.json", help="问题文件路径")
    parser.add_argument("--category", default=None, help="只评估指定场景 (FACT/FINANCIAL/OPERATION/RESEARCH/REASONING/ANALYSIS)")

    args = parser.parse_args()

    if args.category:
        # 只评估指定分类的问题
        with open(args.questions, 'r', encoding='utf-8') as f:
            data = json.load(f)
        category = args.category.upper()
        q_cats = data.get("question_categories", {})
        filtered = [q for q in data["questions"] if q_cats.get(q) == category]
        if not filtered:
            print(f"未找到场景 {category} 的问题")
            sys.exit(1)
        print(f"仅评估场景: {category} ({len(filtered)}题)")
        # 临时修改问题文件
        import tempfile, shutil
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8')
        filtered_data = {
            "questions": filtered,
            "question_categories": {q: category for q in filtered},
            "ground_truth": {q: data["ground_truth"][q] for q in filtered if q in data.get("ground_truth", {})}
        }
        json.dump(filtered_data, tmp, ensure_ascii=False, indent=2)
        tmp.close()
        try:
            run_evaluation(args.config, tmp.name)
        finally:
            Path(tmp.name).unlink()
    else:
        run_evaluation(args.config, args.questions)
