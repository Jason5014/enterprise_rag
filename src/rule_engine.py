"""通用规则引擎 - 从YAML配置读取规则，动态解释执行"""
import re
from typing import Dict, Any, List, Optional
from enum import Enum


class RuleCondition(Enum):
    ANY_MATCH = "any_match"
    ALL_MATCH = "all_match"
    PATTERN = "pattern"


class RuleEngine:
    """通用规则引擎"""

    def __init__(self, rules: List[Dict[str, Any]]):
        self.rules = rules

    def evaluate(self, text: str) -> Optional[Dict[str, Any]]:
        """
        评估文本，返回匹配的第一条规则
        """
        for rule in self.rules:
            matched = self._check_rule(rule, text)
            if matched:
                return {"rule": rule, "matched": matched}
        return None

    def _check_rule(self, rule: Dict[str, Any], text: str) -> Optional[Any]:
        """检查单条规则"""
        condition = rule.get("condition", "any_match")
        keywords = rule.get("keywords", [])
        pattern = rule.get("pattern", "")

        if condition == "any_match":
            for kw in keywords:
                if kw in text:
                    return kw
            return None
        elif condition == "all_match":
            matched = []
            for kw in keywords:
                if kw in text:
                    matched.append(kw)
            return matched if len(matched) == len(keywords) else None
        elif condition == "pattern":
            m = re.search(pattern, text)
            return m.group() if m else None
        return None


def load_rules_from_yaml(yaml_path: str) -> List[Dict[str, Any]]:
    """从YAML文件加载规则配置"""
    import yaml
    with open(yaml_path, 'r', encoding='utf-8') as f:
        conf = yaml.safe_load(f)
    return conf.get("query_classification", {}).get("rules", [])


def load_sections_from_yaml(yaml_path: str) -> List[Dict[str, Any]]:
    """从YAML文件加载分段解析配置"""
    import yaml
    with open(yaml_path, 'r', encoding='utf-8') as f:
        conf = yaml.safe_load(f)
    return conf.get("response_parsing", {}).get("sections", [])