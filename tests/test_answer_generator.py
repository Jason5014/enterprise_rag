"""答案生成模块测试"""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestQueryRouter:
    """QueryRouter测试"""

    def test_init(self):
        """测试初始化"""
        from src.query_router import QueryRouter, QueryType
        from config.retrieval_config import RetrievalConfig

        config = RetrievalConfig()
        router = QueryRouter(config=config)
        assert router.model == "qwen-turbo"

    def test_query_type_enum(self):
        """测试问题类型枚举"""
        from src.query_router import QueryType

        assert QueryType.NAME.value == "name"
        assert QueryType.NUMBER.value == "number"
        assert QueryType.BOOLEAN.value == "boolean"
        assert QueryType.NAMES.value == "names"
        assert QueryType.COMPARATIVE.value == "comparative"
        assert QueryType.UNKNOWN.value == "unknown"

    @patch('src.query_router.DASHSCOPE_AVAILABLE', False)
    def test_rule_based_classify_number(self):
        """测试规则分类-数值型"""
        from src.query_router import QueryRouter, QueryType

        router = QueryRouter()
        result = router._rule_based_classify("中芯国际2024年营收是多少？")
        assert result["type"] == QueryType.NUMBER

    @patch('src.query_router.DASHSCOPE_AVAILABLE', False)
    def test_rule_based_classify_boolean(self):
        """测试规则分类-是否型"""
        from src.query_router import QueryRouter, QueryType

        router = QueryRouter()
        result = router._rule_based_classify("公司有没有并购？")
        assert result["type"] == QueryType.BOOLEAN

    @patch('src.query_router.DASHSCOPE_AVAILABLE', False)
    def test_rule_based_classify_comparative(self):
        """测试规则分类-比较型"""
        from src.query_router import QueryRouter, QueryType

        router = QueryRouter()
        result = router._rule_based_classify("华为和中芯哪个更好？")
        assert result["type"] == QueryType.COMPARATIVE

    @patch('src.query_router.DASHSCOPE_AVAILABLE', False)
    def test_rule_based_classify_names(self):
        """测试规则分类-列表型"""
        from src.query_router import QueryRouter, QueryType

        router = QueryRouter()
        result = router._rule_based_classify("有哪些子公司？")
        assert result["type"] == QueryType.NAMES

    @patch('src.query_router.DASHSCOPE_AVAILABLE', False)
    def test_rule_based_classify_unknown(self):
        """测试规则分类-未知"""
        from src.query_router import QueryRouter, QueryType

        router = QueryRouter()
        result = router._rule_based_classify("今天天气怎么样")
        assert result["type"] == QueryType.UNKNOWN


class TestPromptBuilder:
    """PromptBuilder测试"""

    def test_build_name_prompt(self):
        """测试名称型Prompt构建"""
        from src.query_router import PromptBuilder

        prompt = PromptBuilder.build_name_prompt("公司CEO是谁？", ["文档内容"])
        assert "公司CEO是谁？" in prompt
        assert "文档内容" in prompt

    def test_build_number_prompt(self):
        """测试数值型Prompt构建"""
        from src.query_router import PromptBuilder

        prompt = PromptBuilder.build_number_prompt("营收多少？", ["上下文"])
        assert "营收多少？" in prompt
        assert "上下文" in prompt
        assert "推理过程" in prompt

    def test_build_boolean_prompt(self):
        """测试是否型Prompt构建"""
        from src.query_router import PromptBuilder

        prompt = PromptBuilder.build_boolean_prompt("是否上市？", ["上下文"])
        assert "是否上市？" in prompt
        assert "上下文" in prompt

    def test_build_names_prompt(self):
        """测试列表型Prompt构建"""
        from src.query_router import PromptBuilder

        prompt = PromptBuilder.build_names_prompt("有哪些子公司？", ["上下文"])
        assert "有哪些子公司？" in prompt
        assert "上下文" in prompt
        assert "列表：" in prompt

    def test_build_comparative_prompt(self):
        """测试比较型Prompt构建"""
        from src.query_router import PromptBuilder

        prompt = PromptBuilder.build_comparative_prompt("哪家更高？", ["上下文"])
        assert "哪家更高？" in prompt
        assert "上下文" in prompt
        assert "对比分析" in prompt


class TestAnswerGenerator:
    """AnswerGenerator测试"""

    def test_init(self):
        """测试初始化"""
        from src.answer_generator import AnswerGenerator
        from config.answer_config import AnswerConfig

        answer_config = AnswerConfig(answer_model="qwen-turbo", temperature=0.1)
        generator = AnswerGenerator(answer_config=answer_config)
        assert generator.model == "qwen-turbo"
        assert generator.temperature == 0.1

    def test_generate_with_empty_context(self):
        """测试空上下文"""
        from src.answer_generator import AnswerGenerator

        generator = AnswerGenerator()
        result = generator.generate("问题", [])

        assert result["final_answer"] == "N/A"
        assert result["used_parent_chunks"] == []

    def test_generate_with_context(self):
        """测试有上下文生成"""
        from src.answer_generator import AnswerGenerator

        generator = AnswerGenerator()
        context = [
            {"text": "相关内容", "chunk_id": "c1", "parent_id": "p1", "score": 0.9}
        ]

        # 无dashscope时应该返回fallback
        with patch('src.answer_generator.DASHSCOPE_AVAILABLE', False):
            result = generator.generate("问题", context)

        assert "step_by_step_analysis" in result
        assert "reasoning_summary" in result
        assert "final_answer" in result

    def test_build_prompt_number(self):
        """测试数值型Prompt构建"""
        from src.answer_generator import AnswerGenerator
        from src.query_router import QueryType

        generator = AnswerGenerator()
        prompt = generator._build_prompt("营收多少？", ["上下文"], QueryType.NUMBER)
        assert "推理过程" in prompt

    def test_build_prompt_name(self):
        """测试名称型Prompt构建"""
        from src.answer_generator import AnswerGenerator
        from src.query_router import QueryType

        generator = AnswerGenerator()
        prompt = generator._build_prompt("CEO是谁？", ["上下文"], QueryType.NAME)
        assert "直接给出答案" in prompt

    def test_parse_response(self):
        """测试响应解析"""
        from src.answer_generator import AnswerGenerator

        generator = AnswerGenerator()
        response = """推理过程：
1. 分析上下文
2. 提取数据
3. 计算结果

最终答案：
500亿元"""

        context = [{"metadata": {"page": 1}}]
        result = generator._parse_response(response, context)

        assert "step_by_step_analysis" in result
        assert "final_answer" in result

    def test_fallback_result(self):
        """测试降级结果"""
        from src.answer_generator import AnswerGenerator

        generator = AnswerGenerator()
        result = generator._fallback_result()

        assert result["final_answer"] == "N/A"
        assert "服务暂时不可用" in result["reasoning_summary"]


class TestConversationHistory:
    """ConversationHistory测试"""

    def test_init(self):
        """测试初始化"""
        from src.answer_generator import ConversationHistory

        history = ConversationHistory(max_turns=5, max_tokens=4000)
        assert history.max_turns == 5
        assert history.max_tokens == 4000
        assert history.history == []

    def test_add(self):
        """测试添加对话"""
        from src.answer_generator import ConversationHistory

        history = ConversationHistory()
        history.add("user", "你好")
        history.add("assistant", "你好，有什么可以帮助你的？")

        assert len(history.history) == 2
        assert history.history[0]["role"] == "user"
        assert history.history[1]["role"] == "assistant"

    def test_get_context(self):
        """测试获取上下文"""
        from src.answer_generator import ConversationHistory

        history = ConversationHistory(max_turns=2)
        history.add("user", "第一个问题")
        history.add("assistant", "第一个回答")
        history.add("user", "第二个问题")
        history.add("assistant", "第二个回答")

        context = history.get_context()
        assert "第二个问题" in context
        assert "第二个回答" in context
        assert "第一个问题" not in context  # 被截断

    def test_get_context_empty(self):
        """测试空历史获取上下文"""
        from src.answer_generator import ConversationHistory

        history = ConversationHistory()
        context = history.get_context()
        assert context is None

    def test_clear(self):
        """测试清空历史"""
        from src.answer_generator import ConversationHistory

        history = ConversationHistory()
        history.add("user", "你好")
        history.clear()
        assert len(history.history) == 0

    def test_get_history_count(self):
        """测试获取历史轮数"""
        from src.answer_generator import ConversationHistory

        history = ConversationHistory()
        history.add("user", "问题1")
        history.add("assistant", "回答1")
        history.add("user", "问题2")
        history.add("assistant", "回答2")

        assert history.get_history_count() == 2

    def test_trim(self):
        """测试自动修剪"""
        from src.answer_generator import ConversationHistory

        history = ConversationHistory(max_turns=2)
        for i in range(10):
            history.add("user", f"问题{i}")
            history.add("assistant", f"回答{i}")

        # 应该只保留最后4条
        assert len(history.history) <= 4

    def test_context_truncation(self):
        """测试上下文截断"""
        from src.answer_generator import ConversationHistory

        history = ConversationHistory(max_tokens=50)
        history.add("user", "A" * 100)
        history.add("assistant", "B" * 100)

        context = history.get_context()
        # 上下文应该被截断到max_tokens
        assert len(context) <= 100


class TestAnswerConfig:
    """AnswerConfig测试"""

    def test_default_config(self):
        """测试默认配置"""
        from config.answer_config import AnswerConfig

        config = AnswerConfig()
        assert config.answer_model == "qwen-turbo"
        assert config.temperature == 0.1
        assert config.max_tokens == 2000
        assert config.min_steps == 5
        assert config.min_words == 150

    def test_config_validation(self):
        """测试配置验证"""
        from config.answer_config import AnswerConfig

        config = AnswerConfig(temperature=0.5)
        assert config.validate() is True

    def test_config_invalid_temperature(self):
        """测试无效温度"""
        from config.answer_config import AnswerConfig

        config = AnswerConfig(temperature=5.0)
        with pytest.raises(ValueError):
            config.validate()


class TestIntegration:
    """集成测试"""

    def test_full_answer_generation_flow(self):
        """测试完整答案生成流程"""
        from src.answer_generator import AnswerGenerator
        from src.query_router import QueryType

        generator = AnswerGenerator()

        context = [
            {"text": "公司2024年营收500亿元", "chunk_id": "c1", "parent_id": "p1", "score": 0.9, "metadata": {"page": 5}},
            {"text": "同比增长20%", "chunk_id": "c2", "parent_id": "p1", "score": 0.8, "metadata": {"page": 5}}
        ]

        # Mock禁用LLM
        with patch('src.answer_generator.DASHSCOPE_AVAILABLE', False):
            result = generator.generate("2024年营收是多少？", context)

        assert "step_by_step_analysis" in result
        assert "final_answer" in result
        assert result["used_parent_chunks"] == ["p1"]

    def test_multi_turn_conversation(self):
        """测试多轮对话"""
        from src.answer_generator import ConversationHistory
        from src.answer_generator import AnswerGenerator

        history = ConversationHistory(max_turns=10)  # 足够大以保留所有历史

        # 第一轮
        history.add("user", "中芯国际2024年营收是多少？")
        history.add("assistant", "500亿元")

        # 第二轮（指代消解）
        history.add("user", "那研发投入呢？")
        history.add("assistant", "50亿元")

        assert history.get_history_count() == 2
        context = history.get_context()
        assert "中芯国际" in context
        assert "研发投入" in context


if __name__ == "__main__":
    pytest.main([__file__, "-v"])