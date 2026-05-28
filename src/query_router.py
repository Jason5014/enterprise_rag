"""Query路由模块 - 纯LLM分类，无任何硬编码匹配"""
import os
import logging
from typing import Dict, Any, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)

try:
    import dashscope
    from dashscope import Generation
    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False

from config.retrieval_config import RetrievalConfig


class QueryType(Enum):
    """问题类型枚举"""
    NAME = "name"          # 单一实体名称
    NUMBER = "number"      # 数值
    BOOLEAN = "boolean"    # 是否
    NAMES = "names"        # 列表
    COMPARATIVE = "comparative"  # 比较
    UNKNOWN = "unknown"


class PromptBuilder:
    """Prompt构建器 - 简化版，统一格式"""

    @staticmethod
    def build_prompt(query: str, context: List[str], query_type: QueryType) -> str:
        """构建统一格式的Prompt"""
        context_text = "\n\n".join([f"[文档{i+1}]\n{c}" for i, c in enumerate(context)])

        # 根据问题类型添加特定要求
        type_requirements = {
            QueryType.NAME: "直接回答名称，如果有多个用顿号分隔",
            QueryType.NUMBER: "给出具体数值和单位",
            QueryType.BOOLEAN: "回答是或否，并简要说明理由",
            QueryType.NAMES: "逐条列出，每条一行",
            QueryType.COMPARATIVE: "列出对比双方的关键信息，给出结论",
        }

        requirement = type_requirements.get(query_type, "根据上下文回答问题")

        return f"""基于以下上下文回答问题。

上下文：
{context_text}

问题：{query}

要求：{requirement}
如果上下文中没有相关信息，回答"N/A"。

答案："""


class QueryRouter:
    """Query路由 - 纯LLM分类"""

    def __init__(self, config: Optional[RetrievalConfig] = None):
        self.config = config or RetrievalConfig()
        self.model = "qwen-turbo"
        self._system_prompt = None

    @property
    def system_prompt(self) -> str:
        """动态生成系统提示"""
        if self._system_prompt is None:
            type_descs = {
                "NAME": "询问单一实体名称（公司名、人名、机构名、股票代码等）",
                "NUMBER": "询问具体数值（金额、人数、比例、增长率等）",
                "BOOLEAN": "询问是否/有没有（判断是或否）",
                "NAMES": "询问多个事项（列举、列出、有哪些）",
                "COMPARATIVE": "询问比较（哪个更高、哪个更好等）",
            }

            lines = [
                "你是一个问题分类专家。根据用户问题判断其类型。",
                "",
                "问题类型定义："
            ]
            for qt in QueryType:
                if qt != QueryType.UNKNOWN:
                    lines.append(f"- {qt.name}: {type_descs.get(qt.name, '')}")

            lines.extend([
                "",
                "示例：",
                "- \"审计机构是哪家\" → NAME",
                "- \"营收是多少\" → NUMBER",
                "- \"是否上市\" → BOOLEAN",
                "- \"有哪些风险\" → NAMES",
                "- \"和华为比哪个更强\" → COMPARATIVE",
                "",
                "输出格式（只输出这三行）：",
                "类型: NAME/NUMBER/BOOLEAN/NAMES/COMPARATIVE",
                "置信度: 0.0-1.0",
                "理由: 一句话说明"
            ])
            self._system_prompt = "\n".join(lines)

        return self._system_prompt

    def classify(self, query: str) -> Dict[str, Any]:
        """纯LLM分类"""
        if not DASHSCOPE_AVAILABLE:
            return {"type": QueryType.UNKNOWN, "confidence": 0.0, "reason": "LLM不可用"}

        try:
            api_key = self._get_api_key()
            logger.debug("QueryRouter 调用LLM分类: '%s'", query)

            response = Generation.call(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": query}
                ],
                api_key=api_key,
                result_format="message"
            )

            if response.status_code == 200:
                content = response.output.choices[0].message.content.strip()
                logger.debug("分类结果: %s", content)
                return self._parse_response(content)
            else:
                return {"type": QueryType.UNKNOWN, "confidence": 0.0, "reason": f"API错误: {response.status_code}"}

        except Exception as e:
            if "ConnectionError" in type(e).__name__ or "NameResolutionError" in str(e) or "MaxRetryError" in str(e):
                logger.warning("Query分类 API不可用: %s", type(e).__name__)
            else:
                logger.debug("分类异常: %s", e)
            return {"type": QueryType.UNKNOWN, "confidence": 0.0, "reason": str(e)}

    def _parse_response(self, content: str) -> Dict[str, Any]:
        """解析LLM响应"""
        result = {"type": QueryType.UNKNOWN, "confidence": 0.0, "reason": ""}

        for line in content.split("\n"):
            line = line.strip()
            if not line or ":" not in line:
                continue

            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()

            if key == "类型":
                val_upper = val.upper()
                for qt in QueryType:
                    if qt.name == val_upper:
                        result["type"] = qt
                        break
            elif key == "置信度":
                try:
                    conf = float(val.replace("%", ""))
                    result["confidence"] = conf / 100 if conf > 1 else conf
                except:
                    pass
            elif key == "理由":
                result["reason"] = val

        return result

    def _get_api_key(self) -> str:
        """获取API密钥"""
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
        if not api_key or api_key == "your_dashscope_api_key_here":
            raise ValueError("请在.env设置DASHSCOPE_API_KEY")
        return api_key
