"""答案评估模块 - 评估RAG系统输出质量"""
import json
import os
import re
import logging
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
from datetime import datetime
import numpy as np

try:
    from dashscope import Generation
    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False

from config.eval_config import EvalConfig
from config.retrieval_config import RetrievalConfig

logger = logging.getLogger(__name__)


class Evaluator:
    """RAG系统评估器"""

    def __init__(self, config: Optional[EvalConfig] = None, retrieval_config: Optional[RetrievalConfig] = None):
        self.config = config or EvalConfig()
        self.retrieval_config = retrieval_config or RetrievalConfig()
        self.eval_model = self.config.eval_model
        self.top_k_list = self.config.eval_top_k

    def evaluate_retrieval(
        self,
        queries: List[str],
        ground_truth: Dict[str, List[str]],
        retrieval_func: Callable[[str], List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """
        评估检索质量

        Args:
            queries: 查询列表
            ground_truth: ground_truth[query] = [relevant_chunk_ids]
            retrieval_func: 检索函数，签名为 (query) -> List[Dict]

        Returns:
            检索评估指标
        """
        metrics = {f"recall@{k}": [] for k in self.top_k_list}
        metrics.update({f"hit@{k}": [] for k in self.top_k_list})
        metrics["mrr"] = []
        metrics["ndcg@5"] = []

        for query in queries:
            retrieved = retrieval_func(query)
            relevant = set(ground_truth.get(query, []))

            if not relevant:
                continue

            # 计算各个指标
            retrieved_ids = [r.get("chunk_id", "") for r in retrieved]

            # Recall@K & Hit@K
            for k in self.top_k_list:
                retrieved_k = set(retrieved_ids[:k])
                hit_count = len(retrieved_k & relevant)
                recall = hit_count / len(relevant) if relevant else 0
                metrics[f"recall@{k}"].append(recall)
                metrics[f"hit@{k}"].append(1.0 if hit_count > 0 else 0.0)

            # MRR
            mrr_score = 0
            for i, rid in enumerate(retrieved_ids):
                if rid in relevant:
                    mrr_score = 1 / (i + 1)
                    break
            metrics["mrr"].append(mrr_score)

            # NDCG@5
            dcg = 0
            for i, rid in enumerate(retrieved_ids[:5]):
                if rid in relevant:
                    dcg += 1 / np.log2(i + 2)  # i+2因为从1开始
            idcg = sum(1 / np.log2(i + 2) for i in range(min(5, len(relevant))))
            ndcg = dcg / idcg if idcg > 0 else 0
            metrics["ndcg@5"].append(ndcg)

        # 计算平均值
        result = {}
        for metric_name, values in metrics.items():
            if values:
                result[metric_name] = sum(values) / len(values)
            else:
                result[metric_name] = 0.0

        return result

    def evaluate_answer(
        self,
        questions: List[Dict[str, str]],
        answer_func: Callable[[str], Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        评估答案质量

        Args:
            questions: 问题列表，每项包含 question, expected_answer 等
            answer_func: 答案生成函数

        Returns:
            答案评估指标
        """
        exact_match_scores = []
        f1_scores = []

        for q in questions:
            question_text = q.get("question", "")
            expected = q.get("expected_answer", "").lower().strip()

            result = answer_func(question_text)
            predicted = result.get("final_answer", "N/A")
            if isinstance(predicted, str):
                predicted = predicted.lower().strip()

            # Exact Match
            em = 1.0 if predicted == expected else 0.0
            exact_match_scores.append(em)

            # F1 Score
            expected_tokens = set(expected.split())
            predicted_tokens = set(predicted.split()) if predicted != "N/A" else set()
            if expected_tokens and predicted_tokens:
                precision = len(expected_tokens & predicted_tokens) / len(predicted_tokens)
                recall = len(expected_tokens & predicted_tokens) / len(expected_tokens)
                f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            else:
                f1 = 1.0 if predicted == expected else 0.0
            f1_scores.append(f1)

        return {
            "exact_match": sum(exact_match_scores) / len(exact_match_scores) if exact_match_scores else 0,
            "f1": sum(f1_scores) / len(f1_scores) if f1_scores else 0
        }

    def evaluate_citation_accuracy(
        self,
        questions: List[Dict[str, Any]],
        answer_func: Callable[[str], Dict[str, Any]]
    ) -> float:
        """
        评估引用准确性 - LLM声称的页码是否真实存在于检索结果中

        Args:
            questions: 问题列表
            answer_func: 答案生成函数

        Returns:
            引用准确率
        """
        correct = 0
        total = 0

        for q in questions:
            question_text = q.get("question", "")
            result = answer_func(question_text)

            claimed_pages = result.get("relevant_pages", [])
            retrieved_results = result.get("retrieved_context", [])

            retrieved_pages = {r.get("page") for r in retrieved_results if r.get("page")}

            # 检查声称的页码是否都在检索结果中
            valid_pages = [p for p in claimed_pages if p in retrieved_pages]

            if len(valid_pages) == len(claimed_pages):
                correct += 1
            total += 1

        return correct / total if total > 0 else 0.0

    def generate_eval_report(
        self,
        retrieval_metrics: Dict[str, float],
        answer_metrics: Dict[str, float],
        citation_accuracy: float,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成评估报告

        Args:
            retrieval_metrics: 检索指标
            answer_metrics: 答案指标
            citation_accuracy: 引用准确率
            output_path: 可选的输出路径

        Returns:
            评估报告字典
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "retrieval_metrics": retrieval_metrics,
            "answer_metrics": answer_metrics,
            "citation_accuracy": citation_accuracy,
            "overall_score": (
                retrieval_metrics.get("recall@5", 0) * 0.3 +
                answer_metrics.get("f1", 0) * 0.5 +
                citation_accuracy * 0.2
            ),
            "improvements": []
        }

        # 生成改进建议
        if retrieval_metrics.get("recall@5", 0) < 0.7:
            report["improvements"].append("检索召回率偏低，建议增加表格内容权重或调整chunk大小")

        if answer_metrics.get("exact_match", 0) < 0.5:
            report["improvements"].append("答案准确率偏低，建议优化答案生成Prompt或增加推理步骤")

        if citation_accuracy < 0.8:
            report["improvements"].append("引用准确性偏低，建议校验页码引用")

        # 保存报告
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

        return report


class RetrievalEvaluator:
    """检索评估器 - 专门评估检索阶段质量"""

    def __init__(self, top_k: List[int] = None):
        self.top_k = top_k or [1, 3, 5, 10]

    def compute_recall(self, retrieved: List[str], relevant: List[str], k: int) -> float:
        """计算Recall@K（命中数/预期总数）"""
        retrieved_k = set(retrieved[:k])
        relevant_set = set(relevant)
        if not relevant_set:
            return 0.0
        return len(retrieved_k & relevant_set) / len(relevant_set)

    def compute_hit(self, retrieved: List[str], relevant: List[str], k: int) -> float:
        """计算Hit@K（Top-K中是否至少命中一个，1或0）"""
        retrieved_k = set(retrieved[:k])
        relevant_set = set(relevant)
        if not relevant_set:
            return 0.0
        return 1.0 if retrieved_k & relevant_set else 0.0

    def compute_mrr(self, retrieved: List[str], relevant: List[str]) -> float:
        """计算MRR (Mean Reciprocal Rank)"""
        for i, r in enumerate(retrieved):
            if r in relevant:
                return 1.0 / (i + 1)
        return 0.0

    def compute_ndcg(
        self,
        retrieved: List[str],
        relevant: List[str],
        k: int = 5
    ) -> float:
        """计算NDCG@K"""
        dcg = 0.0
        for i, r in enumerate(retrieved[:k]):
            if r in relevant:
                dcg += 1.0 / np.log2(i + 2)

        idcg = sum(1.0 / np.log2(i + 2) for i in range(min(k, len(relevant))))
        return dcg / idcg if idcg > 0 else 0.0

    def evaluate(
        self,
        queries: List[str],
        relevant_chunks: Dict[str, List[str]],
        retrieval_func: Callable[[str], List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """
        综合评估检索质量

        Args:
            queries: 查询列表
            relevant_chunks: 每个查询的相关chunk id字典
            retrieval_func: 检索函数

        Returns:
            各项检索指标
        """
        all_metrics = {f"recall@{k}": [] for k in self.top_k}
        all_metrics.update({f"hit@{k}": [] for k in self.top_k})
        all_metrics["mrr"] = []
        all_metrics["ndcg@5"] = []

        for query in queries:
            retrieved_results = retrieval_func(query)
            retrieved_ids = [r.get("chunk_id", "") for r in retrieved_results]
            relevant = relevant_chunks.get(query, [])

            if not relevant:
                continue

            for k in self.top_k:
                all_metrics[f"recall@{k}"].append(self.compute_recall(retrieved_ids, relevant, k))
                all_metrics[f"hit@{k}"].append(self.compute_hit(retrieved_ids, relevant, k))

            all_metrics["mrr"].append(self.compute_mrr(retrieved_ids, relevant))
            all_metrics["ndcg@5"].append(self.compute_ndcg(retrieved_ids, relevant, k=5))

        # 计算平均值
        avg_metrics = {}
        for metric_name, values in all_metrics.items():
            avg_metrics[metric_name] = sum(values) / len(values) if values else 0.0

        return avg_metrics


class LLMJudgeEvaluator:
    """LLM-as-Judge 评估器 - 使用LLM评估答案质量"""

    def __init__(self, config: Optional[EvalConfig] = None):
        self.config = config or EvalConfig()
        self.model = self.config.eval_model
        self._api_key = None

    def _get_api_key(self) -> str:
        """获取API密钥"""
        if self._api_key is None:
            from dotenv import load_dotenv
            load_dotenv()
            self._api_key = os.getenv("DASHSCOPE_API_KEY", "")
            if not self._api_key or self._api_key == "your_dashscope_api_key_here":
                raise ValueError("请在.env中设置DASHSCOPE_API_KEY")
        return self._api_key

    def _call_llm(self, prompt: str) -> str:
        """调用LLM"""
        if not DASHSCOPE_AVAILABLE:
            raise RuntimeError("dashscope未安装")

        api_key = self._get_api_key()
        response = Generation.call(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            api_key=api_key,
            result_format="message"
        )

        if response.status_code == 200:
            return response.output.choices[0].message.content.strip()
        else:
            raise RuntimeError(f"API调用失败: {response.message}")

    def _parse_score(self, response: str) -> float:
        """从LLM响应中解析分数"""
        # 使用配置的正则模式
        match = re.search(self.config.score_pattern, response)
        if match:
            score = float(match.group(1))
            return min(max(score, 0.0), 1.0)

        # 尝试提取单独的数字
        numbers = re.findall(r'\d+\.?\d*', response)
        if numbers:
            score = float(numbers[0])
            if 0 <= score <= 1:
                return score
            elif 0 <= score <= 10:
                return score / 10.0

        return 0.5  # 默认中间值

    def _parse_reason(self, response: str) -> str:
        """从LLM响应中解析理由"""
        match = re.search(self.config.reason_pattern, response)
        return match.group(1).strip() if match else ""

    def evaluate_faithfulness(
        self,
        question: str,
        answer: str,
        context: str
    ) -> Dict[str, Any]:
        """
        评估答案忠实度

        Args:
            question: 问题
            answer: 答案
            context: 检索到的上下文

        Returns:
            {"score": float, "reason": str}
        """
        prompt = self.config.faithfulness_prompt.format(
            context=context[:self.config.context_max_chars],
            question=question,
            answer=answer
        )

        try:
            response = self._call_llm(prompt)
            score = self._parse_score(response)
            reason = self._parse_reason(response)
            return {"score": score, "reason": reason}
        except Exception as e:
            logger.error("忠实度评估失败: %s", e)
            return {"score": 0.0, "reason": str(e)}

    def evaluate_relevance(
        self,
        question: str,
        answer: str
    ) -> Dict[str, Any]:
        """
        评估答案相关性

        Args:
            question: 问题
            answer: 答案

        Returns:
            {"score": float, "reason": str}
        """
        prompt = self.config.relevance_prompt.format(
            question=question,
            answer=answer
        )

        try:
            response = self._call_llm(prompt)
            score = self._parse_score(response)
            reason = self._parse_reason(response)
            return {"score": score, "reason": reason}
        except Exception as e:
            logger.error("相关性评估失败: %s", e)
            return {"score": 0.0, "reason": str(e)}

    def evaluate_completeness(
        self,
        question: str,
        predicted_answer: str,
        reference_answer: str
    ) -> Dict[str, Any]:
        """
        评估答案完整性

        Args:
            question: 问题
            predicted_answer: 预测答案
            reference_answer: 参考答案

        Returns:
            {"score": float, "reason": str}
        """
        prompt = self.config.completeness_prompt.format(
            question=question,
            reference_answer=reference_answer,
            predicted_answer=predicted_answer
        )

        try:
            response = self._call_llm(prompt)
            score = self._parse_score(response)
            reason = self._parse_reason(response)
            return {"score": score, "reason": reason}
        except Exception as e:
            logger.error("完整性评估失败: %s", e)
            return {"score": 0.0, "reason": str(e)}

    def evaluate_batch(
        self,
        questions: List[Dict[str, Any]],
        answer_func: Callable[[str], Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        批量评估答案质量

        Args:
            questions: 问题列表，每项包含 question, expected_answer, context 等
            answer_func: 答案生成函数，签名为 (question) -> Dict
            progress_callback: 进度回调函数

        Returns:
            评估结果
        """
        results = {
            "faithfulness": [],
            "relevance": [],
            "completeness": []
        }

        total = len(questions)
        for i, q in enumerate(questions):
            question = q.get("question", "")
            expected_answer = q.get("expected_answer", "")
            context = q.get("context", "")

            # 生成答案
            answer_result = answer_func(question)
            answer = answer_result.get("final_answer", "N/A")

            # 如果没有提供上下文，使用检索到的上下文
            if not context:
                context = "\n".join([
                    ctx.get("text", "")
                    for ctx in answer_result.get("retrieved_context", [])
                ])

            # 评估忠实度
            if context and answer != "N/A":
                faithfulness = self.evaluate_faithfulness(question, answer, context)
                results["faithfulness"].append(faithfulness["score"])

            # 评估相关性
            relevance = self.evaluate_relevance(question, answer)
            results["relevance"].append(relevance["score"])

            # 评估完整性
            if expected_answer:
                completeness = self.evaluate_completeness(question, answer, expected_answer)
                results["completeness"].append(completeness["score"])

            # 进度回调
            if progress_callback:
                progress_callback(i + 1, total)

        # 计算平均值
        return {
            "faithfulness": sum(results["faithfulness"]) / len(results["faithfulness"]) if results["faithfulness"] else 0,
            "relevance": sum(results["relevance"]) / len(results["relevance"]) if results["relevance"] else 0,
            "completeness": sum(results["completeness"]) / len(results["completeness"]) if results["completeness"] else 0,
            "details": results
        }