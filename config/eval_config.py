"""评估配置"""
from dataclasses import dataclass, field
from typing import List, Dict
from .settings import BaseConfig


@dataclass
class EvalConfig(BaseConfig):
    """评估相关配置"""

    # 评估开关
    enabled: bool = False

    # 评估模型
    eval_model: str = "qwen-turbo"

    # 评估指标
    eval_top_k: List[int] = field(default_factory=lambda: [1, 3, 5])

    # 输出配置
    output_dir: str = "data/eval_results"
    save_bad_cases: bool = True

    # 自动评估
    auto_eval_interval: int = 0  # 0表示不自动评估

    # LLM评估Prompt模板
    faithfulness_prompt: str = """你是一个答案忠实度评估专家。请评估以下答案是否基于给定的上下文。

评估标准：
- 1.0分：答案完全基于上下文，所有信息都能在上下文中找到依据
- 0.7分：答案大部分基于上下文，有少量合理推断
- 0.3分：答案部分基于上下文，但有明显推断或添加
- 0.0分：答案包含幻觉，有信息无法在上下文中找到依据

上下文：
{context}

问题：{question}

答案：{answer}

请按以下格式输出：
分数: X.X
理由: 一句话说明"""

    relevance_prompt: str = """你是一个答案相关性评估专家。请评估以下答案是否与问题相关。

评估标准：
- 1.0分：答案完全回答了问题，切中要点
- 0.7分：答案与问题相关，但不够完整或精确
- 0.3分：答案与问题有一定关联，但没有直接回答
- 0.0分：答案与问题完全不相关

问题：{question}

答案：{answer}

请按以下格式输出：
分数: X.X
理由: 一句话说明"""

    completeness_prompt: str = """你是一个答案完整性评估专家。请评估以下答案是否完整回答了问题。

评估标准：
- 1.0分：答案完整回答了问题的所有方面
- 0.7分：答案回答了问题的主要方面，但有遗漏
- 0.3分：答案只回答了问题的部分方面
- 0.0分：答案几乎没有回答问题

问题：{question}

参考答案：{reference_answer}

预测答案：{predicted_answer}

请按以下格式输出：
分数: X.X
理由: 一句话说明"""

    # 评分解析正则
    score_pattern: str = r'分数[：:]\s*(\d+\.?\d*)'
    reason_pattern: str = r'理由[：:]\s*(.+)'

    # 上下文截断长度
    context_max_chars: int = 3000

    def validate(self) -> bool:
        """验证配置合法性"""
        if self.auto_eval_interval < 0:
            raise ValueError("auto_eval_interval must be non-negative")
        if not self.eval_top_k:
            raise ValueError("eval_top_k cannot be empty")
        return True
