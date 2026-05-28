"""答案生成模块 - CoT结构化输出"""
import os
import json
import re
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

try:
    import dashscope
    from dashscope import Generation
    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False

from config.answer_config import AnswerConfig
from config.retrieval_config import RetrievalConfig
from src.query_router import QueryRouter, QueryType, PromptBuilder
from src.utils import get_api_key


class AnswerGenerator:
    """答案生成器 - 使用CoT推理"""

    def __init__(self, answer_config: Optional[AnswerConfig] = None, retrieval_config: Optional[RetrievalConfig] = None):
        self.answer_config = answer_config or AnswerConfig()
        self.retrieval_config = retrieval_config or RetrievalConfig()
        self.model = self.answer_config.answer_model
        self.temperature = self.answer_config.temperature
        self.max_tokens = self.answer_config.max_tokens
        self.min_steps = self.answer_config.min_steps
        self.min_words = self.answer_config.min_words
        self.enable_schema_routing = self.answer_config.enable_schema_routing

        self.query_router = QueryRouter(retrieval_config)

    def generate(self, query: str, context: List[Dict[str, Any]], history: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        生成答案

        Args:
            query: 用户问题
            context: 检索上下文 [{"text": "...", "chunk_id": "...", "score": ...}, ...]
            history: 对话历史 [{"role": "user"/"assistant", "content": "..."}, ...]

        Returns:
            {
                "step_by_step_analysis": str,   # 详细推理过程
                "reasoning_summary": str,       # 50字以内摘要
                "relevant_pages": List[int],   # 引用页码
                "final_answer": str,           # 具体答案
                "used_parent_chunks": List[str] # 使用的父Chunk ID
            }
        """
        # 构建上下文文本
        context_texts = []
        parent_chunk_ids = set()

        for ctx in context:
            text = ctx.get("parent_text", ctx.get("text", ""))
            if text:
                context_texts.append(text)
            if ctx.get("parent_id"):
                parent_chunk_ids.add(ctx["parent_id"])

        if not context_texts:
            return {
                "step_by_step_analysis": "无法找到相关上下文",
                "reasoning_summary": "检索结果为空",
                "relevant_pages": [],
                "final_answer": "N/A",
                "used_parent_chunks": list(parent_chunk_ids)
            }

        # 判断问题类型
        if self.enable_schema_routing:
            classification = self.query_router.classify(query)
            query_type = classification["type"]
            logger.debug("问题类型分类: query='%s' -> type=%s, confidence=%s, reason=%s", query, query_type.value, classification.get('confidence', 0), classification.get('reason', ''))
        else:
            query_type = QueryType.UNKNOWN

        # 构建Prompt
        prompt = self._build_prompt(query, context_texts, query_type)
        logger.debug("使用Prompt类型: %s", query_type.value)

        # 调用LLM
        if DASHSCOPE_AVAILABLE:
            try:
                logger.debug("调用LLM生成答案...")
                response = self._call_llm(prompt, history=history)
                logger.debug("LLM响应长度: %d 字符", len(response))
                logger.debug("LLM响应内容:\n%s...", response[:500])
                result = self._parse_response(response, context)
            except Exception as e:
                if "ConnectionError" in type(e).__name__ or "NameResolutionError" in str(e):
                    logger.warning("答案生成 API不可用: %s", type(e).__name__)
                else:
                    logger.error("LLM调用失败: %s", e)
                result = self._fallback_result()
        else:
            result = self._fallback_result()

        result["used_parent_chunks"] = list(parent_chunk_ids)
        return result

    def _build_prompt(self, query: str, context_texts: List[str], query_type: QueryType) -> str:
        """根据问题类型构建Prompt，按 chunk 边界截断而非字符边界"""
        max_chars = 8000
        selected = []
        total = 0
        for text in context_texts:
            if total + len(text) > max_chars:
                break  # 整块跳过，不截半块
            selected.append(text)
            total += len(text)
        if not selected:
            # 单个 chunk 超长时只截这一个，保证至少有内容
            selected = [context_texts[0][:max_chars]]

        return PromptBuilder.build_prompt(query, selected, query_type)

    def _call_llm(self, prompt: str, history: Optional[List[Dict]] = None) -> str:
        """调用LLM，支持多轮对话历史"""
        api_key = get_api_key()

        messages = []
        if history:
            messages.extend(history)  # 历史轮次在前
        messages.append({"role": "user", "content": prompt})

        response = Generation.call(
            model=self.model,
            messages=messages,
            api_key=api_key,
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )

        if response.status_code == 200:
            return response.output.get("text", "")
        else:
            raise RuntimeError(f"API调用失败: {response.message}")

    def _parse_response(self, response: str, context: List[Dict]) -> Dict[str, Any]:
        """解析LLM响应 - 简化版"""
        result = {
            "step_by_step_analysis": "",
            "reasoning_summary": "",
            "relevant_pages": [],
            "final_answer": "N/A"
        }

        # 查找"答案："标记
        answer_marker = "答案："
        answer_pos = response.find(answer_marker)

        if answer_pos != -1:
            # 有"答案："标记
            before_answer = response[:answer_pos].strip()
            after_answer = response[answer_pos + len(answer_marker):].strip()

            # 提取推理过程（"答案："之前的内容）
            if before_answer:
                # 去掉"推理过程："等前缀
                for prefix in ["推理过程：", "推理过程:", "分析：", "分析:"]:
                    if before_answer.startswith(prefix):
                        before_answer = before_answer[len(prefix):].strip()
                result["step_by_step_analysis"] = before_answer[:500]

            # 提取答案
            result["final_answer"] = after_answer if after_answer else "N/A"
        else:
            # 没有"答案："标记，整个响应就是答案
            result["final_answer"] = response.strip() if response.strip() else "N/A"

        # 提取页码
        for ctx in context:
            page = ctx.get("metadata", {}).get("page")
            if page:
                result["relevant_pages"].append(page)

        return result

    def stream_generate(self, query: str, context: List[Dict[str, Any]],
                        history: Optional[List[Dict]] = None):
        """流式生成答案，逐 token yield 字符串。供 SSE 接口使用。"""
        if not DASHSCOPE_AVAILABLE:
            yield "（DashScope 不可用，无法流式生成）"
            return

        context_texts = []
        for ctx in context:
            text = ctx.get("parent_text", ctx.get("text", ""))
            if text:
                context_texts.append(text)

        if not context_texts:
            yield "未能从知识库中找到相关信息。"
            return

        query_type = QueryType.UNKNOWN
        if self.enable_schema_routing:
            try:
                classification = self.query_router.classify(query)
                query_type = classification["type"]
            except Exception:
                pass

        prompt = self._build_prompt(query, context_texts, query_type)
        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        try:
            api_key = get_api_key()
            response = Generation.call(
                model=self.model,
                messages=messages,
                api_key=api_key,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True,
                incremental_output=True,
            )
            for chunk in response:
                if chunk.status_code == 200:
                    token = chunk.output.get("text", "")
                    if token:
                        yield token
                else:
                    logger.error("流式 API 错误: %s", chunk.message)
                    break
        except Exception as e:
            logger.error("流式生成失败: %s", e)
            yield f"\n（生成中断: {e}）"

    def _fallback_result(self) -> Dict[str, Any]:
        """降级结果"""
        return {
            "step_by_step_analysis": "由于API不可用，无法生成详细推理",
            "reasoning_summary": "服务暂时不可用",
            "relevant_pages": [],
            "final_answer": "N/A"
        }


class ConversationHistory:
    """对话历史管理"""

    def __init__(self, max_turns: int = 5, max_tokens: int = 4000):
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.history: List[Dict[str, str]] = []

    def add(self, role: str, content: str) -> None:
        """添加对话"""
        self.history.append({"role": role, "content": content})
        self._trim()

    def get_context(self) -> Optional[str]:
        """获取历史上下文"""
        if not self.history:
            return None

        context_parts = []
        for turn in self.history[-self.max_turns:]:
            role = "用户" if turn["role"] == "user" else "助手"
            context_parts.append(f"{role}：{turn['content']}")

        context = "\n".join(context_parts)
        if len(context) > self.max_tokens:
            context = context[-self.max_tokens:]

        return context

    def _trim(self) -> None:
        """修剪历史"""
        if len(self.history) > self.max_turns * 2:
            self.history = self.history[-self.max_turns * 2:]

    def clear(self) -> None:
        """清空历史"""
        self.history = []

    def get_history_count(self) -> int:
        """获取历史轮数"""
        return len(self.history) // 2