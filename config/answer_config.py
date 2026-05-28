"""答案生成配置"""
import os
import yaml
from dataclasses import dataclass, field
from typing import List, Dict, Any
from .settings import BaseConfig


def _load_response_parsing_from_yaml() -> Dict[str, Any]:
    """从YAML加载response_parsing配置"""
    config_dir = os.path.dirname(os.path.abspath(__file__))
    yaml_path = os.path.join(config_dir, "query_types.yaml")
    if os.path.exists(yaml_path):
        with open(yaml_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}


@dataclass
class AnswerConfig(BaseConfig):
    """答案生成相关配置"""

    # 模型配置
    answer_model: str = "qwen-turbo"  # 答案生成模型
    temperature: float = 0.1  # 生成温度
    max_tokens: int = 2000  # 最大token数

    # CoT配置
    min_steps: int = 5  # 最少推理步骤数
    min_words: int = 150  # 最少推理字数

    # 引用配置
    min_relevant_pages: int = 1  # 最少引用页码数
    max_relevant_pages: int = 10  # 最多引用页码数

    # Schema路由
    enable_schema_routing: bool = True  # 是否启用Schema路由

    # 响应解析标记（从YAML加载，代码不硬编码）
    analysis_markers: List[str] = field(default_factory=list)
    answer_markers: List[str] = field(default_factory=list)
    stop_markers: List[str] = field(default_factory=list)

    def __post_init__(self):
        conf = _load_response_parsing_from_yaml()
        rp = conf.get("response_parsing", {})

        # 只从YAML加载，不在代码中硬编码任何值
        self.analysis_markers = rp.get("analysis_markers", [])
        self.answer_markers = rp.get("answer_markers", [])
        self.stop_markers = rp.get("stop_markers", [])

    def validate(self) -> bool:
        """验证配置合法性"""
        if self.temperature < 0 or self.temperature > 2:
            raise ValueError("temperature must be between 0 and 2")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.min_steps <= 0:
            raise ValueError("min_steps must be positive")
        return True