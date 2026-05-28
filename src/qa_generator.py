"""QA生成器 - 从文档中自动生成问答对"""
import os
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass
import random

logger = logging.getLogger(__name__)

try:
    import dashscope
    from dashscope import Generation
    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False

from config.retrieval_config import RetrievalConfig


@dataclass
class QAPair:
    """问答对"""
    question: str
    answer: str
    schema: str  # name, number, boolean, names, comparative
    difficulty: str  # easy, medium, hard
    chunk_id: Optional[str] = None
    page: Optional[int] = None


class QAGenerator:
    """QA问答对生成器 - 从文档内容生成测试问答对"""

    SYSTEM_PROMPT = """你是一个问题生成专家。你的任务是基于给定的文档片段，生成多样化的问答对。

要求：
1. 生成不同类型的问题：事实型、推理型、比较型
2. 问题应该简洁明确，答案直接从文档中可获取
3. 每个问答对应标注类型：
   - name: 名称类问题（如人名、公司名、产品名）
   - number: 数值类问题（如营收、人数、比例）
   - boolean: 是否类问题（如是否并购、是否上市）
   - names: 列表类问题（如有哪些产品、高管名单）
   - comparative: 比较类问题（如哪家更高、哪家更低）

4. 难度等级：easy（直接提取）、medium（需要简单计算）、hard（需要多步推理）

输出格式（每行一个问答对，用|分隔）：
[类型]|[难度]|[问题]|[答案]"""

    USER_PROMPT_TEMPLATE = """请基于以下文档片段生成问答对：

---
{context}
---

请生成{num_pairs}个问答对，每行一个，格式为：[类型]|[难度]|[问题]|[答案]"""

    def __init__(self, config: Optional[RetrievalConfig] = None, model: str = "qwen-turbo"):
        self.config = config or RetrievalConfig()
        self.model = model
        self.num_pairs_per_chunk = 2

    def _get_api_key(self) -> str:
        """获取API密钥"""
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
        if not api_key or api_key == "your_dashscope_api_key_here":
            raise ValueError("请在.env中设置DASHSCOPE_API_KEY")
        return api_key

    def generate_from_chunks(
        self,
        chunks: List[Dict[str, Any]],
        num_pairs_per_chunk: int = 2
    ) -> List[QAPair]:
        """
        从分块数据生成问答对

        Args:
            chunks: 分块列表，每项包含 text, chunk_id, metadata
            num_pairs_per_chunk: 每个chunk生成的问答对数量

        Returns:
            问答对列表
        """
        qa_pairs = []

        for chunk in chunks:
            text = chunk.get("text", "")
            chunk_id = chunk.get("chunk_id")
            metadata = chunk.get("metadata", {})
            page = metadata.get("page")

            if len(text) < 50:
                continue

            try:
                pairs = self._generate_from_text(text, num_pairs_per_chunk)
                for q, a, schema, difficulty in pairs:
                    qa_pairs.append(QAPair(
                        question=q,
                        answer=a,
                        schema=schema,
                        difficulty=difficulty,
                        chunk_id=chunk_id,
                        page=page
                    ))
            except Exception as e:
                logger.error("QA生成失败 (chunk_id=%s): %s", chunk_id, e)

        return qa_pairs

    def _generate_from_text(
        self,
        text: str,
        num_pairs: int = 2
    ) -> List[Tuple[str, str, str, str]]:
        """从单个文本片段生成问答对"""
        if not DASHSCOPE_AVAILABLE:
            return self._generate_simple_qa(text, num_pairs)

        text = text[:3000]  # 限制长度

        try:
            response = Generation.call(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": self.USER_PROMPT_TEMPLATE.format(
                        context=text,
                        num_pairs=num_pairs
                    )}
                ],
                api_key=self._get_api_key(),
                result_format="message"
            )

            if response.status_code != 200:
                return self._generate_simple_qa(text, num_pairs)

            content = response.output.choices[0].message.content.strip()
            return self._parse_qa_output(content)

        except Exception as e:
            logger.error("LLM调用失败: %s", e)
            return self._generate_simple_qa(text, num_pairs)

    def _parse_qa_output(self, content: str) -> List[Tuple[str, str, str, str]]:
        """解析LLM输出的问答对"""
        pairs = []
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("|")
            if len(parts) >= 4:
                schema = parts[0].strip()
                difficulty = parts[1].strip()
                question = parts[2].strip()
                answer = parts[3].strip()
                pairs.append((question, answer, schema, difficulty))

        return pairs

    def _generate_simple_qa(
        self,
        text: str,
        num_pairs: int = 2
    ) -> List[Tuple[str, str, str, str]]:
        """简单的问答对生成（当LLM不可用时）"""
        pairs = []

        # 简单模式：生成数值类问题
        import re
        numbers = re.findall(r'\d+[\.,]?\d*[亿万元/人%]?', text)

        if numbers and len(text) > 100:
            # 找到包含数字的句子
            sentences = text.replace("。", "\n").replace("；", "\n").split("\n")
            for sentence in sentences:
                if any(c in sentence for c in numbers[:3]):
                    if len(sentence) > 10:
                        pairs.append((
                            f"文中的数字是多少？",
                            sentence.strip(),
                            "number",
                            "easy"
                        ))
                        break

        if not pairs:
            # 如果没找到数字，返回一个通用问题
            pairs.append((
                "这段文字的主要内容是什么？",
                text[:100] + "..." if len(text) > 100 else text,
                "name",
                "easy"
            ))

        return pairs[:num_pairs]

    def generate_test_set(
        self,
        chunks: List[Dict[str, Any]],
        test_size: int = 50,
        output_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        生成测试集

        Args:
            chunks: 分块列表
            test_size: 测试集大小
            output_path: 可选的输出路径

        Returns:
            测试集列表
        """
        all_qa = self.generate_from_chunks(chunks)

        # 按类型分布
        schema_counts = {}
        for qa in all_qa:
            schema = qa.schema
            schema_counts[schema] = schema_counts.get(schema, 0) + 1

        # 随机采样，但保持类型分布
        sampled_qa = []
        by_schema = {}
        for qa in all_qa:
            if qa.schema not in by_schema:
                by_schema[qa.schema] = []
            by_schema[qa.schema].append(qa)

        # 按比例分配
        per_schema = max(1, test_size // len(by_schema))
        for schema, qa_list in by_schema.items():
            sampled = random.sample(qa_list, min(per_schema, len(qa_list)))
            sampled_qa.extend(sampled)

        # 如果不够，随机补充
        while len(sampled_qa) < test_size and len(all_qa) > len(sampled_qa):
            remaining = [q for q in all_qa if q not in sampled_qa]
            if remaining:
                sampled_qa.append(random.choice(remaining))
            else:
                break

        # 转换为字典格式
        test_set = []
        for qa in sampled_qa[:test_size]:
            test_set.append({
                "question": qa.question,
                "expected_answer": qa.answer,
                "schema": qa.schema,
                "difficulty": qa.difficulty,
                "chunk_id": qa.chunk_id,
                "page": qa.page
            })

        # 保存
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(test_set, f, ensure_ascii=False, indent=2)

        return test_set


class RetrievalEvaluator:
    """检索评估器 - 计算检索相关指标"""

    def __init__(self, top_k: List[int] = None):
        self.top_k = top_k or [1, 3, 5, 10]

    def compute_recall(self, retrieved: List[str], relevant: List[str], k: int) -> float:
        """计算Recall@K"""
        retrieved_k = set(retrieved[:k])
        relevant_set = set(relevant)
        if not relevant_set:
            return 0.0
        return len(retrieved_k & relevant_set) / len(relevant_set)

    def compute_mrr(self, retrieved: List[str], relevant: List[str]) -> float:
        """计算MRR"""
        for i, r in enumerate(retrieved):
            if r in relevant:
                return 1.0 / (i + 1)
        return 0.0

    def compute_ndcg(self, retrieved: List[str], relevant: List[str], k: int = 5) -> float:
        """计算NDCG@K"""
        import numpy as np
        dcg = 0.0
        for i, r in enumerate(retrieved[:k]):
            if r in relevant:
                dcg += 1.0 / np.log2(i + 2)
        idcg = sum(1.0 / np.log2(i + 2) for i in range(min(k, len(relevant))))
        return dcg / idcg if idcg > 0 else 0.0