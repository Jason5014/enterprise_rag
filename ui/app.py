"""Streamlit UI - 企业RAG知识库Web界面"""
import streamlit as st
import json
import time
import copy
from pathlib import Path
from datetime import datetime
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 最先加载环境变量，override=True 确保 .env 文件覆盖系统环境变量
from dotenv import load_dotenv
load_dotenv(override=True)

from config import PRESETS, get_preset, list_presets
from config.settings import ConfigBundle
from config.retrieval_config import RetrievalConfig
from config.answer_config import AnswerConfig
from config.eval_config import EvalConfig
from src.pipeline import RAGPipeline
from src.evaluator import RetrievalEvaluator, LLMJudgeEvaluator
from config.logging_config import LogConfig
from src.logging_setup import init_logging

init_logging(LogConfig(console_level="WARNING"))


# ==================== 指标元数据 ====================

METRIC_INFO = {
    "recall@1": {
        "name": "Recall@1",
        "help": "Top-1 结果命中数占预期总数的比例。预期chunk越多，此值天然越低，需结合 Hit@1 看。",
        "thresholds": (0.4, 0.2),
        "optimize": [
            "启用 Rerank 精排（enable_rerank）— 将正确 chunk 提到第一位",
            "增大 top_k_retrieval 扩大候选池",
            "关注 Hit@1 更直观：只要 Top-1 命中任意一个预期 chunk 即为 1"
        ],
        "low_reasons": [
            "预期 chunk 数多时，Recall@1 天然低（如 5 个预期 chunk 最高 20%）",
            "未启用 Rerank，正确 chunk 排不进第一位",
            "chunk 切分过细，答案被拆到多个 chunk"
        ]
    },
    "hit@1": {
        "name": "Hit@1",
        "help": "Top-1 结果是否命中至少一个预期 chunk（1=命中，0=未命中）。最直观的检索质量指标。",
        "thresholds": (0.8, 0.6),
        "optimize": [
            "启用 Rerank 精排（enable_rerank）— 最有效，将正确 chunk 提到第一位",
            "增大 top_k_retrieval 扩大候选池，给 Rerank 更多选择",
            "检查 Hit@5：如果 Hit@5 也低，说明正确 chunk 未进入候选集"
        ],
        "low_reasons": [
            "未启用 Rerank，正确 chunk 在候选集但排不进第一位",
            "正确 chunk 未被检索到（Embedding/BM25 匹配差）",
            "ground_truth 标注的 chunk 与实际检索结果 ID 不一致"
        ]
    },
    "hit@3": {
        "name": "Hit@3",
        "help": "Top-3 结果中是否至少命中一个预期 chunk。",
        "thresholds": (0.85, 0.7),
        "optimize": [
            "启用 Rerank 精排 — 将正确 chunk 提到 Top-3",
            "启用 MultiQuery 扩展 — 从不同角度召回更多候选",
            "增大 top_k_retrieval（如 20→30）— 扩大候选池"
        ],
        "low_reasons": [
            "正确 chunk 被噪音结果挤出 Top-3",
            "召回面不够广，正确 chunk 未进入候选集"
        ]
    },
    "hit@5": {
        "name": "Hit@5",
        "help": "Top-5 结果中是否至少命中一个预期 chunk。核心检索质量指标。",
        "thresholds": (0.9, 0.75),
        "optimize": [
            "启用 MultiQuery 扩展 — 从不同角度召回更多候选",
            "增大 top_k_retrieval（如 20→50）— 扩大候选池",
            "检查 Embedding 模型是否与文档语言匹配"
        ],
        "low_reasons": [
            "正确 chunk 未进入候选集（top_k 太小或语义匹配差）",
            "Embedding 模型对中文语义理解不足",
            "PDF 解析丢失关键信息"
        ]
    },
    "recall@3": {
        "name": "Recall@3",
        "help": "Top-3 结果命中数占预期总数的比例。建议结合 Hit@3 看。",
        "thresholds": (0.5, 0.3),
        "optimize": [
            "启用 Rerank 精排（enable_rerank）— 将正确 chunk 提到 Top-3",
            "启用 MultiQuery 扩展 — 从不同角度召回更多候选",
            "增大 top_k_retrieval（如 20→30）— 扩大候选池"
        ],
        "low_reasons": [
            "未启用 Rerank，正确 chunk 被噪音结果挤出 Top-3",
            "召回面不够广，正确 chunk 未进入候选集",
            "MultiQuery 生成的变体查询质量不高"
        ]
    },
    "recall@5": {
        "name": "Recall@5",
        "help": "Top-5 检索结果中包含正确答案的比例。核心检索质量指标。",
        "thresholds": (0.8, 0.6),
        "optimize": [
            "启用 MultiQuery 扩展 — 从不同角度召回更多候选（对 Recall@5 效果显著）",
            "增大 top_k_retrieval（如 20→50）— 扩大候选池",
            "启用 Rerank 精排 — 提升正确 chunk 排名",
            "检查 Embedding 模型是否与文档语言匹配"
        ],
        "low_reasons": [
            "正确 chunk 未进入候选集（top_k 太小或语义匹配差）",
            "MultiQuery 未启用或扩展质量差",
            "Embedding 模型对中文语义理解不足",
            "PDF 解析丢失关键信息"
        ]
    },
    "mrr": {
        "name": "MRR",
        "help": "平均倒排名。第一个正确结果排在第几位的倒数均值。越高说明正确答案越靠前。",
        "thresholds": (0.8, 0.6),
        "optimize": [
            "启用 Rerank 精排（enable_rerank）— 将正确结果排到最前面",
            "调整 BM25 权重（bm25_weight）— 加强关键词精确匹配",
            "优化 chunk 切分策略 — 提升单 chunk 信息密度"
        ],
        "low_reasons": [
            "未启用 Rerank，正确结果被噪音结果挤到后面",
            "存在大量语义相似但不相关的噪音结果",
            "Query 太模糊，导致多个不相关结果排在前面"
        ]
    },
    "ndcg@5": {
        "name": "NDCG@5",
        "help": "归一化折损累计增益。综合考虑相关性和排序位置的质量指标。",
        "thresholds": (0.75, 0.55),
        "optimize": [
            "启用 Rerank 精排 — 改善相关结果的排序位置",
            "启用 MultiQuery 扩展 — 增加相关结果进入 Top-5 的概率",
            "优化 chunk 质量 — 去除噪音 chunk"
        ],
        "low_reasons": [
            "相关结果排序靠后，被噪音结果挤出前列",
            "Top-5 中有大量不相关结果",
            "多个相关结果的相对排序不合理"
        ]
    },
    "faithfulness": {
        "name": "Faithfulness",
        "help": "忠实度。答案是否基于检索到的上下文，有无幻觉。100%表示答案完全有据可查。",
        "thresholds": (0.9, 0.7),
        "optimize": [
            "优化 Answer Prompt — 强调「仅基于上下文回答，不要编造」",
            "降低 temperature（如 0.1→0.05）— 减少创造性",
            "启用 Rerank — 提升上下文相关性，减少噪音干扰",
            "在 Prompt 中加入「如果上下文没有相关信息，请说明」"
        ],
        "low_reasons": [
            "LLM 编造了上下文中不存在的信息（幻觉）",
            "LLM 使用了预训练知识而非检索上下文",
            "检索到的上下文包含噪音，LLM 误提取了错误信息"
        ]
    },
    "relevance": {
        "name": "Relevance",
        "help": "相关性。答案是否切中问题要点，是否真正回答了用户的问题。",
        "thresholds": (0.9, 0.7),
        "optimize": [
            "优化 Query Router — 准确识别问题类型，选择合适的 Prompt 模板",
            "启用 Query 改写 — 让问题更明确",
            "优化检索质量 — 确保上下文与问题匹配"
        ],
        "low_reasons": [
            "答案跑题，回答了不相关的内容",
            "检索到的上下文与问题不匹配",
            "Query Router 分类错误，使用了错误的 Prompt 模板"
        ]
    },
    "completeness": {
        "name": "Completeness",
        "help": "完整性。答案是否涵盖了参考答案的所有要点。低分表示答案遗漏了关键信息。",
        "thresholds": (0.8, 0.6),
        "optimize": [
            "启用 MultiQuery 扩展 — 从不同角度召回，覆盖更多要点",
            "增大 top_k_retrieval — 召回更多上下文",
            "在 Prompt 中要求「全面回答，不要遗漏关键信息」",
            "检查 context_max_chars 是否过小导致上下文被截断"
        ],
        "low_reasons": [
            "检索召回不足，关键信息未被检索到",
            "上下文过长被截断（context_max_chars 限制）",
            "参考答案包含多个要点，但只回答了部分"
        ]
    }
}


def _metric_color(value, thresholds):
    """根据阈值返回颜色 (green/yellow/red)"""
    good, ok = thresholds
    if value >= good:
        return "green"
    elif value >= ok:
        return "orange"
    else:
        return "red"


def _metric_badge(value, thresholds):
    """返回带颜色的指标徽章 HTML"""
    color = _metric_color(value, thresholds)
    color_map = {"green": "#28a745", "orange": "#fd7e14", "red": "#dc3545"}
    return f'<span style="color:{color_map[color]};font-weight:bold">{value:.1%}</span>'


def _render_metric_card(col, metric_key, value):
    """渲染单个指标卡片（带 help tooltip 和颜色）"""
    info = METRIC_INFO.get(metric_key)
    if not info:
        col.metric(metric_key, f"{value:.2%}")
        return

    color = _metric_color(value, info["thresholds"])
    emoji = {"green": "🟢", "orange": "🟡", "red": "🔴"}[color]

    with col:
        st.metric(
            info["name"],
            f"{value:.1%}",
            help=info["help"]
        )
        st.caption(f"{emoji} {'优秀' if color == 'green' else '良好' if color == 'orange' else '需优化'}")


def _render_metric_analysis(metric_key, value):
    """渲染指标分析（优化方向 + 可能原因）"""
    info = METRIC_INFO.get(metric_key)
    if not info:
        return

    color = _metric_color(value, info["thresholds"])
    if color == "green":
        return  # 优秀时不显示优化建议

    with st.expander(f"🔍 {info['name']} 分析与优化建议", expanded=(color == "red")):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**可能原因：**")
            for reason in info["low_reasons"]:
                st.markdown(f"- {reason}")
        with c2:
            st.markdown("**优化方向：**")
            for tip in info["optimize"]:
                st.markdown(f"- {tip}")


def _compute_overall_score(metrics, has_llm):
    """计算综合评分 (0-100)"""
    scores = []
    weights = []

    # 检索指标 (权重 40%) — 用 Hit@5 替代 Recall@5，更直观
    hit5 = metrics.get("hit@5", 0) or metrics.get("recall@5", 0)
    mrr = metrics.get("mrr", 0)
    if hit5 > 0 or mrr > 0:
        scores.append(hit5 * 50 + mrr * 50)  # 各占 25 分
        weights.append(40)

    # LLM 指标 (权重 60%)
    if has_llm:
        faith = metrics.get("faithfulness", 0)
        relev = metrics.get("relevance", 0)
        compl = metrics.get("completeness", 0)
        if faith > 0 or relev > 0:
            scores.append(faith * 25 + relev * 25 + compl * 10)  # 忠实度和相关性各25分，完整性10分
            weights.append(60)

    if not scores:
        return 0
    return sum(s * w for s, w in zip(scores, weights)) / sum(weights)


# 页面配置
st.set_page_config(
    page_title="企业RAG知识库",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 12px;
        text-align: center;
        margin-bottom: 20px;
    }
    .main-header h1 {
        color: white;
        margin: 0;
        font-size: 2rem;
    }
    .main-header p {
        color: rgba(255,255,255,0.8);
        margin: 5px 0 0 0;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """初始化会话状态"""
    if "history" not in st.session_state:
        st.session_state.history = []
    if "current_config" not in st.session_state:
        st.session_state.current_config = "base"
    if "pipeline" not in st.session_state:
        st.session_state.pipeline = None
    if "retrieval_log" not in st.session_state:
        st.session_state.retrieval_log = None
    if "config_overrides" not in st.session_state:
        # 运行时配置覆盖，格式: {config_name: {param: value}}
        st.session_state.config_overrides = {}
    if "current_view" not in st.session_state:
        st.session_state.current_view = "qa"  # "qa" | "eval"
    if "custom_eval_variants" not in st.session_state:
        st.session_state.custom_eval_variants = []  # [{name, base_preset, overrides}, ...]


def get_pipeline(config_name: str) -> RAGPipeline:
    """获取或创建RAG管道"""
    if st.session_state.pipeline is None or st.session_state.current_config != config_name:
        preset = get_preset(config_name)
        print(f"[DEBUG] 创建新Pipeline，配置: {config_name}")

        # 应用运行时配置覆盖（使用深拷贝避免污染全局 preset）
        overrides = st.session_state.config_overrides.get(config_name, {})
        retrieval_config = copy.deepcopy(preset.retrieval) if preset.retrieval else RetrievalConfig()
        for key, value in overrides.items():
            if hasattr(retrieval_config, key):
                setattr(retrieval_config, key, value)

        # 打印关键配置
        print(f"[DEBUG] enable_multiquery: {retrieval_config.enable_multiquery}")
        print(f"[DEBUG] enable_query_rewrite: {retrieval_config.enable_query_rewrite}")
        print(f"[DEBUG] enable_rerank: {retrieval_config.enable_rerank}")

        config_bundle = ConfigBundle(
            retrieval=retrieval_config,
            answer=preset.answer or AnswerConfig(),
            pdf=preset.pdf,
            embedding=preset.embedding
        )
        st.session_state.pipeline = RAGPipeline(config_bundle)
        st.session_state.current_config = config_name
    return st.session_state.pipeline


def get_system_status():
    """获取系统状态"""
    data_dir = Path("data")

    # 统计向量库（实际存储在chunked/vector_db/）
    vector_db_dir = data_dir / "chunked" / "vector_db"
    vector_count = 0
    if vector_db_dir.exists():
        for f in vector_db_dir.rglob("*"):
            if f.is_file() and f.suffix in [".json", ".index", ".faiss"]:
                vector_count += 1

    # 统计分块
    chunked_file = data_dir / "chunked" / "chunks.json"
    chunk_count = 0
    if chunked_file.exists():
        with open(chunked_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            chunk_count = len(data.get("chunks", []))

    # 统计PDF
    pdf_dir = data_dir / "pdf_reports"
    pdf_count = len(list(pdf_dir.glob("*.pdf"))) if pdf_dir.exists() else 0

    return {
        "pdf_count": pdf_count,
        "chunk_count": chunk_count,
        "vector_ready": vector_count > 0,
        "vector_count": vector_count
    }


def render_config_modal():
    """配置编辑弹窗 - 使用Streamlit原生dialog"""
    @st.dialog("⚙️ 检索配置")
    def config_dialog():
        preset = get_preset(st.session_state.current_config)
        retrieval = preset.retrieval

        if st.session_state.current_config not in st.session_state.config_overrides:
            st.session_state.config_overrides[st.session_state.current_config] = {}

        overrides = st.session_state.config_overrides[st.session_state.current_config]

        st.markdown("### 📋 检索策略配置")

        # ========== 第一组：核心参数 ==========
        st.markdown("**🔢 核心参数**")
        col1, col2 = st.columns(2)
        with col1:
            chunk_size = st.slider(
                "文本块大小",
                value=overrides.get("chunk_size", retrieval.chunk_size),
                min_value=100,
                max_value=1500,
                step=50,
                help="每个文本块包含的字符数"
            )
            overrides["chunk_size"] = chunk_size

        with col2:
            top_k = st.slider(
                "召回数量",
                value=overrides.get("top_k_retrieval", retrieval.top_k_retrieval),
                min_value=5,
                max_value=50,
                step=5,
                help="从向量数据库召回的相关文档数量"
            )
            overrides["top_k_retrieval"] = top_k

        # ========== 第二组：高级功能 ==========
        st.markdown("**⚡ 高级功能**")
        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1:
            enable_parent = st.toggle(
                "📎 父子块",
                value=overrides.get("enable_parent_retrieval", retrieval.enable_parent_retrieval),
                help="关联父级大块内容"
            )
            overrides["enable_parent_retrieval"] = enable_parent

        with col_t2:
            enable_history = st.toggle(
                "💬 对话",
                value=overrides.get("enable_history", retrieval.enable_history),
                help="支持多轮对话"
            )
            overrides["enable_history"] = enable_history

        with col_t3:
            enable_multiquery = st.toggle(
                "🔄 扩展",
                value=overrides.get("enable_multiquery", retrieval.enable_multiquery),
                help="多-query扩展"
            )
            overrides["enable_multiquery"] = enable_multiquery

        col_t4, col_t5 = st.columns(2)
        with col_t4:
            enable_rewrite = st.toggle(
                "✏️ 改写",
                value=overrides.get("enable_query_rewrite", retrieval.enable_query_rewrite),
                help="智能改写查询"
            )
            overrides["enable_query_rewrite"] = enable_rewrite

        with col_t5:
            enable_rerank = st.toggle(
                "🗳️ 重排",
                value=overrides.get("enable_rerank", retrieval.enable_rerank),
                help="LLM二次精排"
            )
            overrides["enable_rerank"] = enable_rerank

        # ========== 第三组：重排与权重 ==========
        if enable_rerank:
            st.markdown("**🎯 重排设置**")
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                rerank_k = st.slider(
                    "精排数量",
                    value=overrides.get("rerank_top_k", retrieval.rerank_top_k),
                    min_value=3,
                    max_value=20,
                    step=1,
                    help="精排后返回的结果数"
                )
                overrides["rerank_top_k"] = rerank_k

            with col_r2:
                use_jina = st.toggle(
                    "🤖 使用Jina",
                    value=overrides.get("use_jina_reranker", retrieval.use_jina_reranker),
                    help="开启则使用Jina Reranker，否则使用LLM重排"
                )
                overrides["use_jina_reranker"] = use_jina

        st.markdown("**⚖️ 检索权重**")
        bm25_w = st.slider(
            "关键词/语义权重",
            value=overrides.get("bm25_weight", retrieval.bm25_weight),
            min_value=0.0,
            max_value=1.0,
            step=0.1,
            help="调节BM25和向量检索的权重"
        )
        overrides["bm25_weight"] = bm25_w

        # 权重可视化
        col_w1, col_w2 = st.columns(2)
        with col_w1:
            st.progress(bm25_w, text=f"关键词 {int(bm25_w*100)}%")
        with col_w2:
            st.progress(1-bm25_w, text=f"语义 {int((1-bm25_w)*100)}%")

        st.markdown("---")

        col_btn1, col_btn2, col_btn3 = st.columns(3)
        with col_btn1:
            if st.button("✅ 保存", use_container_width=True, type="primary"):
                st.session_state.pipeline = None
                st.rerun()
        with col_btn2:
            if st.button("🔄 恢复预设", use_container_width=True):
                st.session_state.config_overrides[st.session_state.current_config] = {}
                st.session_state.pipeline = None
                st.rerun()
        with col_btn3:
            if st.button("❌ 关闭", use_container_width=True):
                st.rerun()

    config_dialog()


def render_sidebar():
    """渲染侧边栏"""
    with st.sidebar:
        st.markdown("## 🏢 企业RAG知识库")

        # 页面导航 - 使用radio + key持久化状态
        st.markdown("### 🧭 导航")
        nav_options = ["💬 问答助手", "📊 评估测试", "🔍 质量监控"]
        view_map = {"问答助手": "qa", "评估测试": "eval", "质量监控": "monitor"}
        current_idx = {"qa": 0, "eval": 1, "monitor": 2}.get(st.session_state.current_view, 0)
        selected_nav = st.radio(
            "选择功能",
            nav_options,
            index=current_idx,
            label_visibility="collapsed",
            key="nav_radio"
        )
        # 从选中文本提取view key
        new_view = "qa"
        for keyword, view_key in view_map.items():
            if keyword in selected_nav:
                new_view = view_key
                break
        if new_view != st.session_state.current_view:
            st.session_state.current_view = new_view
            st.rerun()

        st.markdown("---")
        st.markdown("### 📊 系统状态")

        status = get_system_status()

        col1, col2 = st.columns(2)
        with col1:
            st.metric("文档数", status["pdf_count"])
        with col2:
            st.metric("块数", status["chunk_count"])

        if status["vector_ready"]:
            st.success("✅ 向量库已就绪")
        else:
            st.warning("⚠️ 向量库未就绪")

        # 配置预设选择
        st.markdown("---")
        st.markdown("### 🎯 选择预设方案")

        config_names = list_presets()
        config_descriptions = {
            "base": "基础检索，适合快速测试",
            "fast": "高速模式，禁用高级功能",
            "precision": "高精度，启用所有优化",
            "full": "完整功能，包含评估"
        }

        # 使用radiobuttons更直观
        selected_config = st.radio(
            "选择配置方案：",
            config_names,
            index=config_names.index(st.session_state.current_config) if st.session_state.current_config in config_names else 0,
            format_func=lambda x: f"{x.upper()} - {config_descriptions.get(x, '')}",
            horizontal=True,
            key="config_radio"
        )

        # 当选择变化时自动切换
        if selected_config != st.session_state.current_config:
            st.session_state.current_config = selected_config
            st.session_state.pipeline = None
            st.session_state.config_overrides[selected_config] = {}
            st.rerun()

        st.markdown("---")
        st.markdown("### 🔄 系统操作")
        if st.button("🔄 重新加载 Pipeline", use_container_width=True, help="修改 .env 或配置后点击重新加载", key="reload_pipeline_btn"):
            st.session_state.pipeline = None
            # 强制重新加载环境变量
            from dotenv import load_dotenv
            load_dotenv(override=True)
            st.rerun()

        st.markdown("---")
        st.markdown("### 📈 当前配置")

        # 配置编辑弹窗
        if st.button("📝 编辑参数", use_container_width=True, key="edit_config_btn"):
            st.session_state.config_edit_mode = True

        if st.session_state.get("config_edit_mode", False):
            render_config_modal()

        # 显示当前配置详情（更完整的友好展示）
        preset = get_preset(st.session_state.current_config)
        retrieval = preset.retrieval

        # 初始化当前配置的覆盖值
        if st.session_state.current_config not in st.session_state.config_overrides:
            st.session_state.config_overrides[st.session_state.current_config] = {}

        overrides = st.session_state.config_overrides[st.session_state.current_config]

        # 应用覆盖值显示
        field_names = {f.name for f in retrieval.__dataclass_fields__.values()}
        display_data = {
            k: overrides.get(k, getattr(retrieval, k))
            for k in field_names
        }
        display_retrieval = type(retrieval)(**display_data)

        # 构建更完整的配置展示
        st.markdown("#### 📋 当前配置")

        # 使用expander展示完整配置
        with st.expander("查看详细配置", expanded=True):
            # 基本参数
            st.markdown("**🔢 检索参数**")
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                st.metric("文本块大小", f"{display_retrieval.chunk_size}字符")
            with col_p2:
                st.metric("召回数量", f"{display_retrieval.top_k_retrieval}条")

            # 高级参数
            if display_retrieval.enable_rerank:
                st.metric("精排数量", f"{display_retrieval.rerank_top_k}条")

            st.progress(float(display_retrieval.bm25_weight), text=f"关键词权重 {display_retrieval.bm25_weight:.0%} | 语义权重 {1-display_retrieval.bm25_weight:.0%}")

            st.markdown("---")

            # 功能开关状态
            st.markdown("**⚡ 功能开关**")

            all_features = [
                ("enable_parent_retrieval", "📎 父子块检索", "检索时关联父级大块"),
                ("enable_history", "💬 对话记忆", "支持多轮对话"),
                ("enable_multiquery", "🔄 多-query扩展", "改写为多个相似问法"),
                ("enable_query_rewrite", "✏️ 智能改写", "口语转检索友好型"),
                ("enable_rerank", "🗳️ LLM重排序", "二次精排提高相关性"),
            ]

            for key, label, desc in all_features:
                value = getattr(display_retrieval, key, False)
                status = "✅" if value else "⭕"
                st.markdown(f"{status} **{label}** - {desc if value else '未开启'}")

        st.markdown("---")
        st.markdown("### 🔧 操作")

        if st.button("📚 重新索引", use_container_width=True):
            st.info("请在终端运行: python main.py process-reports")

        if st.button("🗑️ 清空对话", use_container_width=True):
            st.session_state.history = []
            st.rerun()

        st.markdown("---")
        st.markdown("### ℹ️ 关于")
        st.caption("基于 RAG Challenge 获奖方案\n支持 PDF 知识库问答")


def render_answer(answer: dict):
    """渲染答案详情"""
    # 最终答案 - 最重要，放最前面
    final_answer = answer.get("final_answer", "N/A")
    st.markdown("#### ✅ 最终答案")
    st.success(f"**{final_answer}**")

    # 推理过程
    analysis = answer.get("step_by_step_analysis", "")
    if analysis:
        with st.expander("📝 查看推理过程", expanded=False):
            st.markdown(analysis)

    # 引用页码
    pages = answer.get("relevant_pages", [])
    if pages:
        st.caption(f"📄 引用页码: {', '.join(map(str, pages))}")

    st.markdown("---")


def render_retrieval_visualization(log: dict):
    """渲染检索过程可视化"""
    st.markdown("#### 🔍 检索流程")

    stages = log.get("stages", [])
    latency = log.get("latency_ms", {})
    stage_details = log.get("stage_details", [])

    # 构建 stage_name -> detail 的映射
    detail_map = {}
    for detail in stage_details:
        if isinstance(detail, dict):
            name = detail.get("name", "")
            detail_map[name] = detail.get("data", {})

    # 检索流程横条
    cols = st.columns(len(stages) + 1)
    for i, stage in enumerate(stages):
        with cols[i]:
            if isinstance(stage, str):
                name = stage
            else:
                name = stage.get("name", "")
            duration = latency.get(name, 0)
            st.markdown(f"""
            <div style="text-align: center; background: white; border-radius: 8px; padding: 12px 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="font-size: 1.5rem;">{get_stage_icon(name)}</div>
                <div style="color: #333; font-weight: bold; font-size: 0.85rem; margin-top: 3px;">{name}</div>
                <div style="color: #666; font-size: 0.75rem;">{duration:.0f}ms</div>
            </div>
            """, unsafe_allow_html=True)
        if i < len(stages) - 1:
            with cols[i]:
                st.markdown("<div style='text-align: center; font-size: 1.2rem; color: #667eea;'>→</div>", unsafe_allow_html=True)
    with cols[-1]:
        st.markdown("""
        <div style="text-align: center; background: #e8f5e9; border-radius: 8px; padding: 12px 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="font-size: 1.5rem;">✅</div>
            <div style="color: #333; font-weight: bold; font-size: 0.85rem;">完成</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # 1. Query 改写详情
    if "query_rewrite" in detail_map:
        qr = detail_map["query_rewrite"]
        original = qr.get("original", "")
        rewritten = qr.get("rewritten", "")
        confidence = qr.get("confidence", 0)
        with st.expander("✏️ Query 改写", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**原始查询**")
                st.code(original, language=None)
            with col2:
                st.markdown(f"**改写结果** (置信度: {confidence:.0%})")
                st.code(rewritten, language=None)

    # 2. MultiQuery 变体
    if "multiquery" in detail_map:
        mq = detail_map["multiquery"]
        variants = mq.get("variants", [])
        with st.expander("🔄 MultiQuery 扩展", expanded=True):
            st.markdown(f"生成 **{len(variants)}** 个查询变体：")
            for i, v in enumerate(variants):
                st.markdown(f"  {i+1}. `{v}`")

    # 3. 检索结果（重排前）
    if "retrieval" in detail_map:
        ret = detail_map["retrieval"]
        ret_count = ret.get("result_count", 0)
        bm25_count = ret.get("bm25_count", 0)
        vector_count = ret.get("vector_count", 0)
        top_results = ret.get("top_results", [])
        with st.expander(f"📦 检索结果（重排前）— 共 {ret_count} 条 | BM25: {bm25_count} | Vector: {vector_count}", expanded=False):
            if top_results:
                for i, r in enumerate(top_results):
                    st.markdown(f"**{i+1}.** `{r.get('chunk_id', '')}` | 分数: {r.get('score', 0):.4f} | 来源: {r.get('source', '')}")
                    st.caption(r.get("text", "")[:200])
            else:
                st.info("无检索结果")

    # 4. 重排结果
    if "rerank" in detail_map:
        rr = detail_map["rerank"]
        rr_count = rr.get("result_count", 0)
        top_score = rr.get("top_score", 0)
        top_results = rr.get("top_results", [])
        with st.expander(f"🎯 重排结果 — 共 {rr_count} 条 | 最高分: {top_score:.4f}", expanded=True):
            if top_results:
                for i, r in enumerate(top_results):
                    st.markdown(f"**{i+1}.** `{r.get('chunk_id', '')}` | 分数: {r.get('score', 0):.4f} | 来源: {r.get('source', '')}")
                    st.caption(r.get("text", "")[:200])
            else:
                st.info("无重排结果")


def get_stage_icon(name: str) -> str:
    """获取阶段图标"""
    icons = {
        "query_rewrite": "✏️",
        "multiquery": "🔍",
        "retrieval": "📦",
        "rerank": "🎯",
        "generate": "🤖",
        "answer": "💡"
    }
    return icons.get(name, "📌")


ERROR_TYPE_OPTIONS = {
    "hallucination": "幻觉 - 编造了不存在的信息",
    "irrelevant": "不相关 - 答非所问",
    "incomplete": "不完整 - 遗漏关键信息",
    "factual_error": "事实错误 - 数据或事实有误",
    "outdated": "过时 - 信息不是最新的",
    "other": "其他"
}


def handle_feedback(answer_id: str, helpful: bool):
    """处理简单反馈（👍）"""
    from src.feedback_collector import FeedbackCollector

    collector = FeedbackCollector()
    for item in st.session_state.history:
        if item.get("answer_id") == answer_id:
            retrieval_log = item.get("retrieval_log", {})
            retrieval_results = None
            if retrieval_log and retrieval_log.get("final_results"):
                retrieval_results = [
                    {"chunk_id": r.get("chunk_id", ""), "score": r.get("score", 0), "page": r.get("metadata", {}).get("page")}
                    for r in retrieval_log.get("final_results", [])[:5]
                ]
            collector.collect(
                query=item.get("query", ""),
                answer=item.get("answer", {}).get("final_answer", ""),
                step_by_step_analysis=item.get("answer", {}).get("step_by_step_analysis"),
                reasoning_summary=item.get("answer", {}).get("reasoning_summary"),
                relevant_pages=item.get("answer", {}).get("relevant_pages", []),
                helpful=helpful,
                session_id=st.session_state.get("session_id", "default"),
                config_name=st.session_state.current_config,
                retrieval_log_id=retrieval_log.get("log_id"),
                retrieval_results=retrieval_results
            )
            break

    st.session_state[f"feedback_done_{answer_id}"] = True
    st.success("感谢您的反馈！")


def handle_bad_feedback(answer_id: str, error_type: str, correct_answer: str, comment: str):
    """处理详细负面反馈（👎表单提交）"""
    from src.feedback_collector import FeedbackCollector

    collector = FeedbackCollector()
    for item in st.session_state.history:
        if item.get("answer_id") == answer_id:
            retrieval_log = item.get("retrieval_log", {})
            retrieval_results = None
            if retrieval_log and retrieval_log.get("final_results"):
                retrieval_results = [
                    {"chunk_id": r.get("chunk_id", ""), "score": r.get("score", 0), "page": r.get("metadata", {}).get("page")}
                    for r in retrieval_log.get("final_results", [])[:5]
                ]
            collector.collect(
                query=item.get("query", ""),
                answer=item.get("answer", {}).get("final_answer", ""),
                step_by_step_analysis=item.get("answer", {}).get("step_by_step_analysis"),
                reasoning_summary=item.get("answer", {}).get("reasoning_summary"),
                relevant_pages=item.get("answer", {}).get("relevant_pages", []),
                helpful=False,
                error_type=error_type if error_type != "other" else None,
                correct_answer=correct_answer.strip() if correct_answer.strip() else None,
                session_id=st.session_state.get("session_id", "default"),
                config_name=st.session_state.current_config,
                retrieval_log_id=retrieval_log.get("log_id"),
                retrieval_results=retrieval_results,
                comment=comment.strip() if comment.strip() else None
            )
            break

    # 清除反馈表单状态
    st.session_state.pop(f"show_bad_form_{answer_id}", None)
    st.success("感谢您的详细反馈，我们会持续改进！")


def check_auto_bad_case(answer: dict) -> list:
    """自动检测潜在Bad Case，返回警告列表"""
    warnings = []
    final_answer = answer.get("final_answer", "")
    relevant_pages = answer.get("relevant_pages", [])
    analysis = answer.get("step_by_step_analysis", "")

    # 检测兜底话术
    fallback_phrases = ["无法找到", "没有相关信息", "未找到", "无法回答", "没有找到", "无法从上下文中", "抱歉", "暂无"]
    for phrase in fallback_phrases:
        if phrase in final_answer:
            warnings.append(f"答案包含兜底话术「{phrase}」，可能未检索到有效信息")
            break

    # 检测无引用
    if not relevant_pages:
        warnings.append("答案未引用任何页码，无法验证来源")

    # 检测推理过程过短
    if len(analysis) < 50:
        warnings.append("推理过程过短，可能跳过了必要分析步骤")

    return warnings


def render_qa_page():
    """问答助手页面"""
    st.markdown("""
    <div class="main-header">
        <h1>🏢 企业RAG知识库</h1>
        <p>基于深度RAG系统 | 支持年报问答 | 向量检索+LLM推理</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 💬 问答助手")
    chat_container = st.container()
    with chat_container:
        for item in st.session_state.history:
            # 用户消息
            with st.chat_message("user"):
                st.markdown(item["query"])

            # AI回答
            with st.chat_message("assistant"):
                render_answer(item["answer"])

                # 自动Bad Case检测
                answer_id = item.get("answer_id", "")
                auto_warnings = check_auto_bad_case(item["answer"])
                if auto_warnings:
                    for w in auto_warnings:
                        st.warning(f"⚠️ {w}")

                # 反馈按钮
                already_feedback = st.session_state.get(f"feedback_done_{answer_id}", False)
                if already_feedback:
                    st.caption("✅ 已收到反馈")
                else:
                    col1, col2, col3 = st.columns([1, 1, 4])
                    with col1:
                        st.button("👍 有用", key=f"good_{answer_id}", on_click=handle_feedback, args=(answer_id, True))
                    with col2:
                        if st.button("👎 有问题", key=f"bad_{answer_id}"):
                            st.session_state[f"show_bad_form_{answer_id}"] = True
                            st.rerun()

                    # 详细反馈表单
                    if st.session_state.get(f"show_bad_form_{answer_id}", False):
                        with st.container():
                            st.markdown("**请告诉我们问题所在：**")
                            error_type = st.selectbox(
                                "错误类型",
                                options=list(ERROR_TYPE_OPTIONS.keys()),
                                format_func=lambda x: ERROR_TYPE_OPTIONS[x],
                                key=f"error_type_{answer_id}"
                            )
                            correct_answer = st.text_area(
                                "正确答案（可选，帮助我们改进）",
                                key=f"correct_{answer_id}",
                                height=80
                            )
                            comment = st.text_input(
                                "补充说明（可选）",
                                key=f"comment_{answer_id}"
                            )
                            fc1, fc2, _ = st.columns([1, 1, 4])
                            with fc1:
                                if st.button("提交反馈", key=f"submit_bad_{answer_id}", type="primary"):
                                    handle_bad_feedback(answer_id, error_type, correct_answer, comment)
                                    st.session_state[f"feedback_done_{answer_id}"] = True
                                    st.rerun()
                            with fc2:
                                if st.button("取消", key=f"cancel_bad_{answer_id}"):
                                    st.session_state.pop(f"show_bad_form_{answer_id}", None)
                                    st.rerun()

            # 检索过程
            if item.get("retrieval_log"):
                with st.expander("🔍 查看检索过程"):
                    render_retrieval_visualization(item["retrieval_log"])

            st.markdown("---")

    st.markdown("### 💭 提问")
    user_input = st.text_area(
        "输入您的问题",
        placeholder="例如：中芯国际2024年营收是多少？",
        height=100,
        key="user_input"
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        submit_btn = st.button("🚀 发送", type="primary", use_container_width=True)
    with col2:
        clear_btn = st.button("🗑️ 清空", use_container_width=True)

    if clear_btn:
        st.session_state.history = []
        st.rerun()

    if submit_btn and user_input.strip():
        with st.spinner("思考中..."):
            try:
                print(f"[DEBUG] 当前配置: {st.session_state.current_config}")
                print(f"[DEBUG] Pipeline缓存状态: {st.session_state.pipeline is not None}")
                pipeline = get_pipeline(st.session_state.current_config)
                print(f"[DEBUG] Pipeline配置 - enable_query_rewrite: {pipeline.retrieval_config.enable_query_rewrite}")
                print(f"[DEBUG] Pipeline配置 - enable_multiquery: {pipeline.retrieval_config.enable_multiquery}")
                print(f"[DEBUG] Pipeline配置 - enable_rerank: {pipeline.retrieval_config.enable_rerank}")
                start_time = time.time()
                result = pipeline.answer_single_question(user_input)
                elapsed = time.time() - start_time
                retrieval_log = pipeline.get_last_retrieval_log() if hasattr(pipeline, 'get_last_retrieval_log') else None
                answer_id = f"ans_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
                st.session_state.history.append({
                    "query": user_input,
                    "answer": result,
                    "answer_id": answer_id,
                    "retrieval_log": retrieval_log,
                    "elapsed_ms": elapsed * 1000
                })
                st.rerun()
            except Exception as e:
                st.error(f"处理失败: {str(e)}")
                import traceback
                st.code(traceback.format_exc())

    st.markdown("---")
    st.caption(f"当前配置: {st.session_state.current_config} | 企业RAG知识库 v0.1.0")


def render_eval_page():
    """评估测试页面"""
    st.markdown("""
    <div class="main-header">
        <h1>📊 评估测试</h1>
        <p>测试RAG检索质量 | Recall@K / MRR / NDCG / Faithfulness / Relevance</p>
    </div>
    """, unsafe_allow_html=True)

    eval_file = Path("data/eval_questions.json")
    if eval_file.exists():
        with open(eval_file, 'r', encoding='utf-8') as f:
            eval_data = json.load(f)
        all_questions = eval_data.get("questions", [])
        ground_truth = eval_data.get("ground_truth", {})
        question_categories = eval_data.get("question_categories", {})
        categories_meta = eval_data.get("categories", {})
        has_ground_truth = bool(ground_truth)
    else:
        all_questions = []
        ground_truth = {}
        question_categories = {}
        categories_meta = {}
        has_ground_truth = False

    # 场景分类筛选
    if categories_meta:
        cat_options = ["全部"] + list(categories_meta.keys())
        selected_cat = st.selectbox(
            "场景分类筛选",
            cat_options,
            format_func=lambda x: f"{x} - {categories_meta[x]}" if x != "全部" else "全部（所有场景）",
            key="eval_cat_filter"
        )
        if selected_cat == "全部":
            questions = all_questions
        else:
            questions = [q for q in all_questions if question_categories.get(q) == selected_cat]
    else:
        questions = all_questions

    col_info, col_btn = st.columns([2, 1])
    with col_info:
        if questions:
            st.markdown(f"**测试问题:** {len(questions)} 个" + (f"（场景: {selected_cat}）" if categories_meta and selected_cat != "全部" else ""))
            if has_ground_truth:
                st.success("✅ ground_truth 已标注，可计算完整指标")
            else:
                st.warning("⚠️ 暂无 ground_truth 标注，仅显示延迟统计")
        else:
            st.error("❌ 未找到评估问题文件: data/eval_questions.json")

    # 评估模式切换
    eval_mode = st.radio(
        "评估模式",
        ["单配置评估", "多配置对比", "自定义变体对比"],
        index=0,
        horizontal=True,
        label_visibility="collapsed",
        key="eval_mode_radio"
    )

    compare_configs = []
    if eval_mode == "多配置对比":
        all_configs = list_presets()
        compare_configs = st.multiselect(
            "选择要对比的配置（至少选2个）",
            all_configs,
            default=[c for c in ["base", "precision"] if c in all_configs],
            format_func=lambda x: x.upper()
        )
        if len(compare_configs) < 2:
            st.info("请至少选择2个配置进行对比")

    # LLM评估选项
    col_llm, col_btn = st.columns([2, 1])
    with col_llm:
        enable_llm_eval = st.checkbox(
            "启用 LLM-as-Judge 评估（Faithfulness / Relevance / Completeness）",
            value=False,
            help="使用LLM评估答案质量，会增加API调用",
            key="enable_llm_eval_cb"
        )

    with col_btn:
        run_btn = st.button("▶️ 开始评估", type="primary", use_container_width=True)

    # 自定义变体管理
    if eval_mode == "自定义变体对比":
        st.markdown("##### ➕ 添加配置变体（基于 base 预设）")

        def _make_variant_name(overrides: dict) -> str:
            """从参数覆盖自动生成变体名称"""
            parts = []
            for k, v in overrides.items():
                if k == "enable_multiquery" and v is False:
                    parts.append("mq=off")
                elif k == "enable_query_rewrite" and v is False:
                    parts.append("rw=off")
                elif k == "enable_rerank" and v is False:
                    parts.append("rerank=off")
                elif k == "use_jina_reranker" and v is True:
                    parts.append("jina=on")
                elif k == "bm25_weight":
                    parts.append(f"bm25={v:.2f}")
                elif k == "top_k_retrieval":
                    parts.append(f"topk={v}")
                elif k == "rerank_top_k":
                    parts.append(f"rk={v}")
            return ",".join(parts) if parts else "默认参数"

        with st.expander("点击添加新变体", expanded=not st.session_state.custom_eval_variants):
            st.markdown("**参数覆盖（只记录与base不同的）**")
            c1, c2 = st.columns(2)
            with c1:
                v_multiquery = st.checkbox("多Query扩展", value=True, key="v_multiquery")
                v_rewrite = st.checkbox("查询改写", value=True, key="v_rewrite")
                v_rerank = st.checkbox("重排", value=True, key="v_rerank")
            with c2:
                v_jina = st.checkbox("Jina重排", value=False, key="v_jina")
                v_bm25 = st.number_input("关键词权重(BM25)", 0.0, 1.0, 0.3, 0.05, key="v_bm25")

            c3, c4 = st.columns(2)
            with c3:
                v_topk = st.number_input("召回数量", 5, 50, 20, key="v_topk")
            with c4:
                v_rerankk = st.number_input("重排数量", 1, 20, 5, key="v_rerankk")

            add_variants = st.button("✅ 添加变体", use_container_width=True)
            if add_variants:
                # 重排关闭时，强制禁用 Jina 重排
                if not v_rerank:
                    v_jina = False
                overrides = {
                    "enable_multiquery": v_multiquery,
                    "enable_query_rewrite": v_rewrite,
                    "enable_rerank": v_rerank,
                    "use_jina_reranker": v_jina,
                    "bm25_weight": v_bm25,
                    "top_k_retrieval": v_topk,
                    "rerank_top_k": v_rerankk,
                }
                # 只保留与 base 预设不同的 overrides
                base_preset = get_preset("base")
                base_rc = base_preset.retrieval or RetrievalConfig()
                filtered = {}
                for k, v in overrides.items():
                    base_val = getattr(base_rc, k, None)
                    if base_val != v:
                        filtered[k] = v
                v_name = _make_variant_name(filtered)
                st.session_state.custom_eval_variants.append({
                    "name": v_name,
                    "base_preset": st.session_state.current_config,
                    "overrides": filtered
                })
                st.rerun()

        # 显示已添加变体
        if st.session_state.custom_eval_variants:
            st.markdown("##### 📋 待测变体列表")
            for i, v in enumerate(st.session_state.custom_eval_variants):
                col_del, col_info = st.columns([1, 5])
                with col_del:
                    if st.button("🗑️", key=f"del_var_{i}"):
                        del st.session_state.custom_eval_variants[i]
                        st.rerun()
                with col_info:
                    override_str = ", ".join([f"{k}={v}" for k, v in v["overrides"].items()]) if v["overrides"] else "（默认参数）"
                    st.markdown(f"**{v['name']}** | {override_str}")
            st.info(f"共 {len(st.session_state.custom_eval_variants)} 个变体待测")
        else:
            st.info("请先添加至少1个变体，再点击「开始评估」")

    st.markdown("---")

    def _run_eval_for_config(config_name: str, extra_overrides: dict = None, progress_callback=None, enable_llm_eval=False):
        """对单个配置运行评估"""
        preset = get_preset(config_name)
        runtime_overrides = st.session_state.config_overrides.get(config_name, {})
        # 深拷贝避免修改全局 preset 对象
        retrieval_config = copy.deepcopy(preset.retrieval) if preset.retrieval else RetrievalConfig()
        for k, v in runtime_overrides.items():
            if hasattr(retrieval_config, k):
                setattr(retrieval_config, k, v)
        if extra_overrides:
            for k, v in extra_overrides.items():
                if hasattr(retrieval_config, k):
                    setattr(retrieval_config, k, v)
            # enable_rerank=False 时，强制禁用 jina 重排
            if not retrieval_config.enable_rerank:
                retrieval_config.use_jina_reranker = False

        config_bundle = ConfigBundle(
            retrieval=retrieval_config,
            answer=preset.answer or AnswerConfig(),
            pdf=preset.pdf,
            embedding=preset.embedding
        )
        pipeline = RAGPipeline(config_bundle)
        retrieval_func = lambda q, p=pipeline: p.retrieve(q, top_k=20)
        evaluator = RetrievalEvaluator(top_k=[1, 3, 5, 10])

        # LLM评估器
        llm_judge = None
        if enable_llm_eval:
            eval_config = preset.eval_config if preset.eval_config else EvalConfig()
            llm_judge = LLMJudgeEvaluator(config=eval_config)

        all_m = {f"recall@{k}": [] for k in [1, 3, 5, 10]}
        all_m.update({f"hit@{k}": [] for k in [1, 3, 5, 10]})
        all_m["mrr"] = []
        all_m["ndcg@5"] = []
        if enable_llm_eval:
            all_m["faithfulness"] = []
            all_m["relevance"] = []
            all_m["completeness"] = []
        # 按场景分类收集分数
        cat_m = {}
        q_results = []
        latencies = []
        total = len(questions)

        for idx, q in enumerate(questions):
            if progress_callback:
                progress_callback(idx, total, q)
            cat = question_categories.get(q, "UNKNOWN")
            start = time.time()
            results = retrieval_func(q)
            elapsed = (time.time() - start) * 1000
            latencies.append(elapsed)
            retrieved_ids = [r.get("chunk_id", "") for r in results[:10]]
            relevant = ground_truth.get(q, {}).get("relevant_chunks", [])
            expected_answer = ground_truth.get(q, {}).get("answer", "")

            # 初始化分类指标
            if cat not in cat_m:
                cat_m[cat] = {f"recall@{k}": [] for k in [1, 3, 5, 10]}
                cat_m[cat].update({f"hit@{k}": [] for k in [1, 3, 5, 10]})
                cat_m[cat]["mrr"] = []
                cat_m[cat]["ndcg@5"] = []
                if enable_llm_eval:
                    cat_m[cat]["faithfulness"] = []
                    cat_m[cat]["relevance"] = []
                    cat_m[cat]["completeness"] = []

            print(f"  Q: {q[:40]} | results={len(results)} | retrieved={len(retrieved_ids)} | relevant={len(relevant)}", file=sys.stderr)

            q_result = {
                "query": q,
                "category": cat,
                "retrieved_ids": retrieved_ids,
                "latency_ms": elapsed,
                "result_count": len(results),
                "relevant_count": len(relevant),
                "is_hit": bool(set(retrieved_ids[:5]) & set(relevant)) if relevant else False,
                "top1": retrieved_ids[0] if retrieved_ids else None
            }

            # LLM评估
            if enable_llm_eval and llm_judge:
                # 获取完整答案
                rag_result = pipeline.answer_single_question(q, return_retrieval_details=True)
                answer = rag_result.get("final_answer", "N/A")
                retrieval_details = rag_result.get("retrieval_details", {})
                context = "\n".join([
                    ctx.get("text", "")
                    for ctx in retrieval_details.get("retrieval_results", [])
                ])

                # 忠实度评估
                if context and answer != "N/A":
                    faith = llm_judge.evaluate_faithfulness(q, answer, context)
                    all_m["faithfulness"].append(faith["score"])
                    cat_m[cat]["faithfulness"].append(faith["score"])
                    q_result["faithfulness"] = faith

                # 相关性评估
                relevance = llm_judge.evaluate_relevance(q, answer)
                all_m["relevance"].append(relevance["score"])
                cat_m[cat]["relevance"].append(relevance["score"])
                q_result["relevance"] = relevance

                # 完整性评估
                if expected_answer:
                    completeness = llm_judge.evaluate_completeness(q, answer, expected_answer)
                    all_m["completeness"].append(completeness["score"])
                    cat_m[cat]["completeness"].append(completeness["score"])
                    q_result["completeness"] = completeness

            q_results.append(q_result)

            if relevant:
                for k in [1, 3, 5, 10]:
                    recall_val = evaluator.compute_recall(retrieved_ids, relevant, k)
                    hit_val = evaluator.compute_hit(retrieved_ids, relevant, k)
                    all_m[f"recall@{k}"].append(recall_val)
                    all_m[f"hit@{k}"].append(hit_val)
                    cat_m[cat][f"recall@{k}"].append(recall_val)
                    cat_m[cat][f"hit@{k}"].append(hit_val)
                mrr_val = evaluator.compute_mrr(retrieved_ids, relevant)
                all_m["mrr"].append(mrr_val)
                cat_m[cat]["mrr"].append(mrr_val)
                ndcg_val = evaluator.compute_ndcg(retrieved_ids, relevant, k=5)
                all_m["ndcg@5"].append(ndcg_val)
                cat_m[cat]["ndcg@5"].append(ndcg_val)

        if progress_callback:
            progress_callback(total, total, "完成")

        avg_m = {name: sum(v) / len(v) if v else 0.0 for name, v in all_m.items()}

        # 计算分类平均指标
        cat_avg_m = {}
        for cat, scores in cat_m.items():
            cat_avg_m[cat] = {name: sum(v) / len(v) if v else 0.0 for name, v in scores.items()}
            cat_avg_m[cat]["count"] = len(cat_m[cat]["relevance"]) if enable_llm_eval else len(cat_m[cat].get("recall@5", []))

        print(f"\n=== 评估开始 ({config_name}) ===", file=sys.stderr)
        print(f"问题数: {len(questions)}, ground_truth: {len(ground_truth)}", file=sys.stderr)
        for i, qr in enumerate(q_results):
            print(f"Q{i+1}: {qr['query'][:30]} | hit={qr.get('is_hit')} | top1={qr.get('top1')} | count={qr.get('result_count')}", file=sys.stderr)
        print(f"=== 评估结束 | Recall@5={avg_m.get('recall@5',0):.2%} MRR={avg_m.get('mrr',0):.2%} ===\n", file=sys.stderr)

        return {
            "config": config_name,
            "question_count": len(questions),
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
            "min_latency_ms": min(latencies) if latencies else 0,
            "max_latency_ms": max(latencies) if latencies else 0,
            "query_results": q_results,
            "ground_truth_available": has_ground_truth,
            "metrics": avg_m,
            "category_metrics": cat_avg_m,
            "categories_meta": categories_meta,
            "llm_eval_enabled": enable_llm_eval,
            "pipeline_config": {
                "enable_multiquery": retrieval_config.enable_multiquery,
                "enable_rerank": retrieval_config.enable_rerank,
                "use_jina_reranker": retrieval_config.use_jina_reranker,
                "bm25_weight": retrieval_config.bm25_weight,
                "top_k_retrieval": retrieval_config.top_k_retrieval
            }
        }

    if run_btn and questions:
        if eval_mode == "多配置对比" and len(compare_configs) < 2:
            st.warning("请至少选择2个配置进行对比")
        elif eval_mode == "自定义变体对比" and len(st.session_state.custom_eval_variants) < 1:
            st.warning("请先添加至少1个变体")
        else:
            if eval_mode == "自定义变体对比":
                configs_to_run = [(v.get("base_preset", "base"), v["name"], v["overrides"]) for v in st.session_state.custom_eval_variants]
            elif eval_mode == "多配置对比":
                configs_to_run = [(cfg, cfg, {}) for cfg in compare_configs]
            else:
                configs_to_run = [(st.session_state.current_config, st.session_state.current_config, {})]

            print(f"\n评估 {len(configs_to_run)} 个配置...", file=sys.stderr)
            try:
                all_results = []
                total_configs = len(configs_to_run)
                total_questions = len(questions)
                overall_total = total_configs * total_questions

                progress_bar = st.progress(0)
                status_text = st.empty()
                completed = 0

                for cfg_idx, (cfg_name, display_name, extra_ov) in enumerate(configs_to_run):
                    def _update_progress(q_idx, q_total, q_text):
                        global_completed = cfg_idx * total_questions + q_idx
                        pct = global_completed / overall_total if overall_total > 0 else 0
                        progress_bar.progress(min(pct, 1.0))
                        short_q = q_text[:30] + "..." if len(q_text) > 30 else q_text
                        status_text.markdown(f"**[{cfg_idx+1}/{total_configs}] {display_name}** — {q_idx}/{q_total} ({pct:.0%}) — {short_q}")

                    r = _run_eval_for_config(cfg_name, extra_overrides=extra_ov, progress_callback=_update_progress, enable_llm_eval=enable_llm_eval)
                    r["config"] = display_name
                    all_results.append(r)

                progress_bar.progress(1.0)
                status_text.markdown(f"**评估完成** — {total_configs} 个配置 × {total_questions} 个问题")
                st.session_state.eval_results = all_results
                st.session_state.eval_mode = eval_mode

                # 保存评测结果到历史
                from src.eval_history import EvalHistory
                eval_history = EvalHistory()
                for r in all_results:
                    # 构建配置快照
                    cfg_name = r.get("config", "unknown")
                    preset = get_preset(cfg_name) if cfg_name in ["base", "fast", "precision", "full"] else None
                    config_snapshot = None
                    if preset and preset.retrieval:
                        rc = preset.retrieval
                        config_snapshot = {
                            "chunk_size": rc.chunk_size,
                            "chunk_overlap": rc.chunk_overlap,
                            "bm25_weight": rc.bm25_weight,
                            "vector_weight": rc.vector_weight,
                            "top_k_retrieval": rc.top_k_retrieval,
                            "enable_multiquery": rc.enable_multiquery,
                            "enable_query_rewrite": rc.enable_query_rewrite,
                            "enable_rerank": rc.enable_rerank,
                            "rerank_top_k": rc.rerank_top_k,
                            "enable_parent_retrieval": rc.enable_parent_retrieval,
                        }
                    eval_history.save(
                        config_name=cfg_name,
                        question_count=len(questions),
                        metrics=r.get("metrics", {}),
                        category_metrics=r.get("category_metrics", {}),
                        composite_score=_compute_overall_score(r.get("metrics", {}), r.get("llm_eval_enabled", False)),
                        llm_eval_enabled=r.get("llm_eval_enabled", False),
                        config_snapshot=config_snapshot,
                        questions=questions,
                        query_results=r.get("query_results", []),
                        categories_meta=r.get("categories_meta", {})
                    )
            except Exception as e:
                st.error(f"评估失败: {e}")
                import traceback
                st.code(traceback.format_exc())

    # 显示评估结果
    if st.session_state.get("eval_results"):
        all_results = st.session_state.eval_results
        eval_mode = st.session_state.get("eval_mode", eval_mode)

        if eval_mode in ("多配置对比", "自定义变体对比"):
            # 多配置对比表格
            st.markdown("### 📊 配置对比")
            rows = []
            has_llm_eval = any(r.get("llm_eval_enabled") for r in all_results)
            for r in all_results:
                m = r["metrics"]
                has_llm = r.get("llm_eval_enabled", False)
                overall = _compute_overall_score(m, has_llm)
                row = {
                    "配置": r["config"].upper(),
                    "综合分": f"{overall:.0f}",
                    "Hit@1": f"{m.get('hit@1', 0):.1%}",
                    "Hit@5": f"{m.get('hit@5', 0):.1%}",
                    "Recall@5": f"{m.get('recall@5', 0):.1%}",
                    "MRR": f"{m.get('mrr', 0):.1%}",
                    "NDCG@5": f"{m.get('ndcg@5', 0):.1%}",
                    "平均延迟": f"{r['avg_latency_ms']:.0f}ms"
                }
                if has_llm_eval:
                    row["Faithfulness"] = f"{m.get('faithfulness', 0):.1%}"
                    row["Relevance"] = f"{m.get('relevance', 0):.1%}"
                    row["Completeness"] = f"{m.get('completeness', 0):.1%}"
                rows.append(row)

            import pandas as pd
            df = pd.DataFrame(rows)
            st.dataframe(
                df.set_index("配置"),
                use_container_width=True,
                height=300
            )

            # 找出最佳配置
            st.markdown("**🏆 各项最佳指标：**")
            best_col_info = {}
            for col in ["Recall@1", "Recall@3", "Recall@5", "MRR", "NDCG@5", "平均延迟"]:
                numeric_vals = []
                for r, row in zip(all_results, rows):
                    val = float(row[col].replace("%", "").replace("ms", ""))
                    numeric_vals.append((val, r["config"]))
                if col == "平均延迟":
                    best = min(numeric_vals, key=lambda x: x[0])
                    best_col_info[col] = f"{best[1].upper()} ({best[0]:.1f}ms)"
                else:
                    best = max(numeric_vals, key=lambda x: x[0])
                    best_col_info[col] = f"{best[1].upper()} ({best[0]:.2%})"

            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                st.metric("Recall@5 最佳", best_col_info.get("Recall@5", "-"))
            with bc2:
                st.metric("MRR 最佳", best_col_info.get("MRR", "-"))
            with bc3:
                st.metric("延迟最低", best_col_info.get("平均延迟", "-"))

            # 按场景分类对比
            all_cat_metrics = [r.get("category_metrics", {}) for r in all_results]
            all_cats = set()
            for cm in all_cat_metrics:
                all_cats.update(cm.keys())
            if all_cats:
                st.markdown("---")
                st.markdown("### 📊 按场景分类对比")
                cat_meta = all_results[0].get("categories_meta", {})
                for cat in sorted(all_cats):
                    cat_desc = cat_meta.get(cat, "")
                    with st.expander(f"**[{cat}]** {cat_desc}", expanded=False):
                        cat_rows = []
                        for r, cm in zip(all_results, all_cat_metrics):
                            s = cm.get(cat, {})
                            row = {
                                "配置": r["config"].upper(),
                                "题数": s.get("count", 0),
                                "Hit@1": f"{s.get('hit@1', 0):.2%}",
                                "Hit@5": f"{s.get('hit@5', 0):.2%}",
                                "Recall@5": f"{s.get('recall@5', 0):.2%}",
                                "MRR": f"{s.get('mrr', 0):.2%}",
                            }
                            if has_llm_eval and s.get("relevance"):
                                row["Faithfulness"] = f"{s.get('faithfulness', 0):.2%}"
                                row["Relevance"] = f"{s.get('relevance', 0):.2%}"
                                row["Completeness"] = f"{s.get('completeness', 0):.2%}"
                            cat_rows.append(row)
                        import pandas as pd
                        cat_df = pd.DataFrame(cat_rows)
                        st.dataframe(cat_df.set_index("配置"), use_container_width=True)

            st.markdown("---")
            st.markdown("### 🔍 各配置检索详情")

            for r in all_results:
                with st.expander(f"**📋 {r['config'].upper()} — 检索详情**", expanded=False):
                    for i, qr in enumerate(r["query_results"]):
                        with st.expander(f"Q{i+1}: {qr['query'][:40]}...", expanded=i < 2):
                            st.markdown(f"延迟: {qr['latency_ms']:.1f}ms | Top-1: `{qr['retrieved_ids'][0] if qr['retrieved_ids'] else 'N/A'}`")

                            # 预期 chunk
                            query_text = qr['query']
                            expected_chunks = ground_truth.get(query_text, {}).get("relevant_chunks", [])
                            if expected_chunks:
                                st.markdown(f"**📌 预期 chunk ({len(expected_chunks)}个):**")
                                for ec in expected_chunks:
                                    st.markdown(f"  ✅ `{ec}`")

                            # Top-10 检索结果（匹配的高亮）
                            retrieved = qr['retrieved_ids'][:10]
                            expected_set = set(expected_chunks)
                            hit_in_top10 = set(retrieved) & expected_set
                            miss_in_top10 = expected_set - set(retrieved)

                            st.markdown(f"**🔍 Top-10 检索结果** (命中 {len(hit_in_top10)}/{len(expected_chunks)}):")
                            for j, rid in enumerate(retrieved):
                                rank_marker = "🥇" if j == 0 else "🥈" if j == 1 else "🥉" if j == 2 else f"  {j+1}."
                                if rid in expected_set:
                                    st.markdown(f"  {rank_marker} 🟢 `{rid}` — **命中预期**")
                                else:
                                    st.markdown(f"  {rank_marker} ⚪ `{rid}`")

                            # 未命中的预期 chunk
                            if miss_in_top10:
                                st.markdown(f"**❌ 未进入 Top-10 的预期 chunk ({len(miss_in_top10)}个):**")
                                for mid in miss_in_top10:
                                    st.markdown(f"  ❌ `{mid}`")

        else:
            # 单配置评估
            r = all_results[0]
            results = r
            metrics = r.get("metrics", {})
            has_llm = results.get("llm_eval_enabled", False)

            # ===== 综合评分 =====
            overall = _compute_overall_score(metrics, has_llm)
            score_color = "green" if overall >= 75 else "orange" if overall >= 55 else "red"
            score_label = "优秀" if overall >= 75 else "良好" if overall >= 55 else "需优化"
            st.markdown(f"### 🏆 综合评分: {overall:.0f}/100 ({score_label})")
            st.progress(overall / 100)

            # ===== 检索质量指标 =====
            if results.get("ground_truth_available"):
                st.markdown("### 📈 检索质量")
                m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
                _render_metric_card(m1, "hit@1", metrics.get('hit@1', 0))
                _render_metric_card(m2, "hit@3", metrics.get('hit@3', 0))
                _render_metric_card(m3, "hit@5", metrics.get('hit@5', 0))
                _render_metric_card(m4, "recall@5", metrics.get('recall@5', 0))
                _render_metric_card(m5, "mrr", metrics.get('mrr', 0))
                _render_metric_card(m6, "ndcg@5", metrics.get('ndcg@5', 0))
                with m7:
                    latency = results['avg_latency_ms']
                    lat_color = "green" if latency < 500 else "orange" if latency < 1500 else "red"
                    st.metric("平均延迟", f"{latency:.0f}ms", help="检索+生成总延迟。目标 < 500ms（优秀），< 1500ms（良好）")
                    st.caption(f"{'🟢' if lat_color == 'green' else '🟡' if lat_color == 'orange' else '🔴'} {'优秀' if lat_color == 'green' else '良好' if lat_color == 'orange' else '偏慢'}")

                # 检索指标分析
                for mk in ["hit@1", "hit@5", "recall@5", "mrr", "ndcg@5"]:
                    _render_metric_analysis(mk, metrics.get(mk, 0))
            else:
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("平均延迟", f"{results['avg_latency_ms']:.1f}ms")
                with c2:
                    st.metric("最慢", f"{results['max_latency_ms']:.1f}ms")
                with c3:
                    st.metric("最快", f"{results['min_latency_ms']:.1f}ms")
                st.info("💡 提示: 完善 data/eval_questions.json 中的 ground_truth 可计算 Recall@K 等指标")

            # ===== LLM 评估指标 =====
            if has_llm:
                st.markdown("### 🤖 LLM-as-Judge 评估")
                l1, l2, l3 = st.columns(3)
                _render_metric_card(l1, "faithfulness", metrics.get('faithfulness', 0))
                _render_metric_card(l2, "relevance", metrics.get('relevance', 0))
                _render_metric_card(l3, "completeness", metrics.get('completeness', 0))

                # LLM 指标分析
                for mk in ["faithfulness", "relevance", "completeness"]:
                    _render_metric_analysis(mk, metrics.get(mk, 0))

                # 评估详情
                with st.expander("📋 LLM评估详情", expanded=False):
                    for i, qr in enumerate(results.get("query_results", [])):
                        if "faithfulness" in qr or "relevance" in qr:
                            cat = qr.get("category", "")
                            st.markdown(f"**Q{i+1} [{cat}]: {qr['query'][:50]}...**")
                            cols = st.columns(3)
                            with cols[0]:
                                if "faithfulness" in qr:
                                    s = qr['faithfulness']['score']
                                    c = _metric_color(s, METRIC_INFO["faithfulness"]["thresholds"])
                                    emoji = {"green": "🟢", "orange": "🟡", "red": "🔴"}[c]
                                    st.caption(f"{emoji} 忠实度: {s:.2f}")
                                    st.caption(qr['faithfulness']['reason'][:60])
                            with cols[1]:
                                if "relevance" in qr:
                                    s = qr['relevance']['score']
                                    c = _metric_color(s, METRIC_INFO["relevance"]["thresholds"])
                                    emoji = {"green": "🟢", "orange": "🟡", "red": "🔴"}[c]
                                    st.caption(f"{emoji} 相关性: {s:.2f}")
                                    st.caption(qr['relevance']['reason'][:60])
                            with cols[2]:
                                if "completeness" in qr:
                                    s = qr['completeness']['score']
                                    c = _metric_color(s, METRIC_INFO["completeness"]["thresholds"])
                                    emoji = {"green": "🟢", "orange": "🟡", "red": "🔴"}[c]
                                    st.caption(f"{emoji} 完整性: {s:.2f}")
                                    st.caption(qr['completeness']['reason'][:60])
                            st.markdown("---")

            # 按场景分类指标
            cat_metrics = r.get("category_metrics", {})
            cat_meta = r.get("categories_meta", {})
            if cat_metrics:
                st.markdown("### 📊 按场景分类指标")
                for cat, scores in sorted(cat_metrics.items()):
                    cat_desc = cat_meta.get(cat, "")
                    count = scores.get("count", 0)
                    # 计算分类综合分
                    cat_overall = _compute_overall_score(scores, has_llm)
                    cat_color = "green" if cat_overall >= 75 else "orange" if cat_overall >= 55 else "red"
                    cat_emoji = {"green": "🟢", "orange": "🟡", "red": "🔴"}[cat_color]
                    with st.expander(f"**[{cat}]** {cat_desc} ({count}题) — 综合分: {cat_emoji}{cat_overall:.0f}", expanded=False):
                        if results.get("ground_truth_available"):
                            cc1, cc2, cc3, cc4, cc5 = st.columns(5)
                            _render_metric_card(cc1, "recall@1", scores.get('recall@1', 0))
                            _render_metric_card(cc2, "recall@3", scores.get('recall@3', 0))
                            _render_metric_card(cc3, "recall@5", scores.get('recall@5', 0))
                            _render_metric_card(cc4, "mrr", scores.get('mrr', 0))
                            _render_metric_card(cc5, "ndcg@5", scores.get('ndcg@5', 0))
                        if results.get("llm_eval_enabled") and scores.get("relevance"):
                            ll1, ll2, ll3 = st.columns(3)
                            _render_metric_card(ll1, "faithfulness", scores.get('faithfulness', 0))
                            _render_metric_card(ll2, "relevance", scores.get('relevance', 0))
                            _render_metric_card(ll3, "completeness", scores.get('completeness', 0))

            st.markdown("### 🔍 检索详情")
            for i, qr in enumerate(results["query_results"]):
                hit_marker = "🟢" if qr.get("is_hit") else "🔴"
                with st.expander(f"{hit_marker} **Q{i+1}:** {qr['query'][:50]}...", expanded=i < 3):
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("延迟", f"{qr['latency_ms']:.1f}ms")
                    with col2:
                        st.metric("命中", "✅ 是" if qr.get("is_hit") else "❌ 否")
                    with col3:
                        st.metric("结果数", qr.get("result_count", 0))
                    with col4:
                        st.metric("Top-1", qr.get("top1", "N/A")[:20] if qr.get("top1") else "N/A")

                    # 预期 chunk
                    query_text = qr['query']
                    expected_chunks = ground_truth.get(query_text, {}).get("relevant_chunks", [])
                    if expected_chunks:
                        st.markdown(f"**📌 预期 chunk ({len(expected_chunks)}个):**")
                        for ec in expected_chunks:
                            st.markdown(f"  ✅ `{ec}`")

                    # Top-10 检索结果（匹配的高亮）
                    retrieved = qr['retrieved_ids'][:10]
                    expected_set = set(expected_chunks)
                    hit_in_top10 = set(retrieved) & expected_set
                    miss_in_top10 = expected_set - set(retrieved)

                    st.markdown(f"**🔍 Top-10 检索结果** (命中 {len(hit_in_top10)}/{len(expected_chunks)}):")
                    for j, rid in enumerate(retrieved):
                        rank_marker = "🥇" if j == 0 else "🥈" if j == 1 else "🥉" if j == 2 else f"  {j+1}."
                        if rid in expected_set:
                            st.markdown(f"  {rank_marker} 🟢 `{rid}` — **命中预期**")
                        else:
                            st.markdown(f"  {rank_marker} ⚪ `{rid}`")

                    # 未命中的预期 chunk
                    if miss_in_top10:
                        st.markdown(f"**❌ 未进入 Top-10 的预期 chunk ({len(miss_in_top10)}个):**")
                        for mid in miss_in_top10:
                            st.markdown(f"  ❌ `{mid}`")
    else:
        st.info("👆 点击上方「开始评估」按钮运行测试")
        st.markdown("""
        **评估指标说明：**

        | 指标 | 说明 | 优秀标准 |
        |------|------|---------|
        | **Recall@K** | Top-K结果中命中的比例 | ≥ 80% |
        | **MRR** | 首个相关结果排位的倒数均值 | ≥ 0.6 |
        | **NDCG@5** | 归一化折损累计增益 | ≥ 0.6 |
        | **延迟** | 检索耗时，越低越好 | < 500ms |
        """)

        if questions:
            st.markdown("**当前问题列表：**")
            for i, q in enumerate(questions):
                st.markdown(f"  {i+1}. {q}")

    st.markdown("---")

    # 显示评估结果
    if st.session_state.get("eval_results"):
        # 统一处理：可能是 list（按钮评估）或 dict（旧版 inline 评估）
        raw_results = st.session_state.eval_results
        if isinstance(raw_results, list):
            results_list = raw_results
        else:
            results_list = [raw_results]

        # 取第一个配置的结果用于主显示
        results = results_list[0]
        metrics = results.get("metrics", {})

        st.markdown("### 📈 评估指标")

        if results.get("ground_truth_available"):
            m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
            _render_metric_card(m1, "hit@1", metrics.get('hit@1', 0))
            _render_metric_card(m2, "hit@3", metrics.get('hit@3', 0))
            _render_metric_card(m3, "hit@5", metrics.get('hit@5', 0))
            _render_metric_card(m4, "recall@5", metrics.get('recall@5', 0))
            _render_metric_card(m5, "mrr", metrics.get('mrr', 0))
            _render_metric_card(m6, "ndcg@5", metrics.get('ndcg@5', 0))
            with m7:
                latency = results['avg_latency_ms']
                lat_color = "green" if latency < 500 else "orange" if latency < 1500 else "red"
                st.metric("平均延迟", f"{latency:.0f}ms", help="检索+生成总延迟。目标 < 500ms（优秀），< 1500ms（良好）")
                st.caption(f"{'🟢' if lat_color == 'green' else '🟡' if lat_color == 'orange' else '🔴'} {'优秀' if lat_color == 'green' else '良好' if lat_color == 'orange' else '偏慢'}")

            # 检索指标分析
            for mk in ["recall@1", "recall@5", "mrr", "ndcg@5"]:
                _render_metric_analysis(mk, metrics.get(mk, 0))
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("平均延迟", f"{results['avg_latency_ms']:.1f}ms")
            with c2:
                st.metric("最慢", f"{results['max_latency_ms']:.1f}ms")
            with c3:
                st.metric("最快", f"{results['min_latency_ms']:.1f}ms")
            st.info("💡 提示: 完善 data/eval_questions.json 中的 ground_truth 可计算 Recall@K 等指标")

        st.markdown("### 🔍 检索详情")

        for i, r in enumerate(results["query_results"]):
            with st.expander(f"**Q{i+1}:** {r['query'][:50]}...", expanded=i < 3):
                col_lat, col_top1 = st.columns([1, 3])
                with col_lat:
                    st.markdown(f"**延迟:** {r['latency_ms']:.1f}ms")
                with col_top1:
                    st.markdown(f"**Top-1:** `{r['retrieved_ids'][0] if r['retrieved_ids'] else 'N/A'}`")

                # 预期 chunk
                query_text = r['query']
                expected_chunks = ground_truth.get(query_text, {}).get("relevant_chunks", [])
                if expected_chunks:
                    st.markdown(f"**📌 预期 chunk ({len(expected_chunks)}个):**")
                    for ec in expected_chunks:
                        st.markdown(f"  ✅ `{ec}`")

                # Top-10 检索结果（匹配的高亮）
                retrieved = r['retrieved_ids'][:10]
                expected_set = set(expected_chunks)
                hit_in_top10 = set(retrieved) & expected_set
                miss_in_top10 = expected_set - set(retrieved)

                st.markdown(f"**🔍 Top-10 检索结果** (命中 {len(hit_in_top10)}/{len(expected_chunks)}):")
                for j, rid in enumerate(retrieved):
                    rank_marker = "🥇" if j == 0 else "🥈" if j == 1 else "🥉" if j == 2 else f"  {j+1}."
                    if rid in expected_set:
                        st.markdown(f"  {rank_marker} 🟢 `{rid}` — **命中预期**")
                    else:
                        st.markdown(f"  {rank_marker} ⚪ `{rid}`")

                # 未命中的预期 chunk
                if miss_in_top10:
                    st.markdown(f"**❌ 未进入 Top-10 的预期 chunk ({len(miss_in_top10)}个):**")
                    for mid in miss_in_top10:
                        st.markdown(f"  ❌ `{mid}`")
    else:
        # 无结果时显示说明
        st.info("👆 点击上方「开始评估」按钮运行测试")
        st.markdown("""
        **评估指标说明：**

        | 指标 | 说明 | 优秀标准 |
        |------|------|---------|
        | **Recall@K** | Top-K结果中命中的比例 | ≥ 80% |
        | **MRR** | 首个相关结果排位的倒数均值 | ≥ 0.6 |
        | **NDCG@5** | 归一化折损累计增益 | ≥ 0.6 |
        | **延迟** | 检索耗时，越低越好 | < 500ms |

        **如何完善 ground_truth：**
        1. 运行一次评估，获取各问题的检索结果
        2. 打开 `data/chunked/chunks.json` 找到相关 chunk 的 ID
        3. 在 `data/eval_questions.json` 的 `ground_truth` 字段中填入
        """)
        if questions:
            st.markdown(f"\n**当前问题列表：**")
            for i, q in enumerate(questions):
                st.markdown(f"  {i+1}. {q}")

    # ===== 评测历史 =====
    st.markdown("---")
    st.markdown("### 📊 评测历史")
    from src.eval_history import EvalHistory
    eval_history = EvalHistory()
    history = eval_history.get_history(limit=20)

    if history:
        # 趋势摘要
        trend = eval_history.get_trend_summary()
        if trend.get("has_trend"):
            latest_c = trend["latest_composite"]
            prev_c = trend["previous_composite"]
            diff = latest_c - prev_c
            arrow = "📈" if diff > 0 else "📉" if diff < 0 else "➡️"
            st.info(f"{arrow} 最近两次评测: {trend['previous_config']}({prev_c:.0f}分) → {trend['latest_config']}({latest_c:.0f}分)，变化 {diff:+.0f}")

        # 历史表格
        import pandas as pd
        table_rows = []
        for r in reversed(history):
            m = r.get("metrics", {})
            table_rows.append({
                "时间": r.get("timestamp", "")[:16].replace("T", " "),
                "配置": r.get("config_name", "").upper(),
                "综合分": f"{r.get('composite_score', 0):.0f}",
                "Hit@1": f"{m.get('hit@1', 0):.1%}",
                "Hit@5": f"{m.get('hit@5', 0):.1%}",
                "Recall@5": f"{m.get('recall@5', 0):.1%}",
                "MRR": f"{m.get('mrr', 0):.1%}",
                "问题数": r.get("question_count", 0)
            })
        df = pd.DataFrame(table_rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # 趋势折线图
        if len(history) >= 2:
            st.markdown("**指标趋势**")
            trend_metrics = st.multiselect(
                "选择对比指标",
                options=["hit@1", "hit@5", "recall@5", "mrr", "faithfulness", "relevance", "completeness"],
                default=["hit@1", "hit@5", "recall@5"],
                key="trend_metric_select"
            )
            if trend_metrics:
                chart_data = eval_history.get_comparison_data(trend_metrics)
                if chart_data:
                    chart_df = pd.DataFrame(chart_data)
                    chart_df["label"] = chart_df["config_name"] + " " + chart_df["timestamp"].str[:10]
                    chart_df = chart_df.set_index("label")[trend_metrics]
                    st.line_chart(chart_df)

        # 详细记录展开
        st.markdown("---")
        st.markdown("**📋 评测详情**")
        for r in reversed(history):
            ts = r.get("timestamp", "")[:16].replace("T", " ")
            cfg = r.get("config_name", "").upper()
            score = r.get("composite_score", 0)
            q_count = r.get("question_count", 0)
            m = r.get("metrics", {})
            eval_id = r.get("eval_id", "")

            score_emoji = "🟢" if score >= 75 else "🟡" if score >= 55 else "🔴"
            with st.expander(f"{score_emoji} **[{cfg}]** {ts} — {score:.0f}分 ({q_count}题)", expanded=False):
                # 配置快照
                config_snap = r.get("config_snapshot")
                if config_snap:
                    st.markdown("**配置参数:**")
                    snap_cols = st.columns(5)
                    snap_items = list(config_snap.items())
                    for ci, (key, val) in enumerate(snap_items):
                        with snap_cols[ci % 5]:
                            st.caption(f"**{key}**: {val}")

                # 指标概览
                m1, m2, m3, m4, m5, m6, m7, m8 = st.columns(8)
                m1.metric("Hit@1", f"{m.get('hit@1', 0):.1%}")
                m2.metric("Hit@3", f"{m.get('hit@3', 0):.1%}")
                m3.metric("Hit@5", f"{m.get('hit@5', 0):.1%}")
                m4.metric("Recall@5", f"{m.get('recall@5', 0):.1%}")
                m5.metric("MRR", f"{m.get('mrr', 0):.1%}")
                m6.metric("NDCG@5", f"{m.get('ndcg@5', 0):.1%}")
                m7.metric("Faith", f"{m.get('faithfulness', 0):.1%}")
                m8.metric("Compl", f"{m.get('completeness', 0):.1%}")

                # 逐题详情
                query_results = r.get("query_results", [])
                if query_results:
                    st.markdown(f"**逐题结果 ({len(query_results)}题):**")
                    for qi, qr in enumerate(query_results):
                        q = qr.get("query", "")
                        cat = qr.get("category", "")
                        hit = qr.get("is_hit", False)
                        latency = qr.get("latency_ms", 0)
                        hit_marker = "✅" if hit else "❌"

                        with st.expander(f"{hit_marker} Q{qi+1}[{cat}]: {q[:40]}... ({latency:.0f}ms)", expanded=False):
                            st.caption(f"**问题:** {q}")
                            st.caption(f"**分类:** {cat} | **延迟:** {latency:.1f}ms | **结果数:** {qr.get('result_count', 0)}")

                            # 检索结果
                            retrieved = qr.get("retrieved_ids", [])
                            if retrieved:
                                st.caption("**Top-5 检索结果:**")
                                for ri, rid in enumerate(retrieved[:5]):
                                    marker = "🥇" if ri == 0 else "🥈" if ri == 1 else "🥉" if ri == 2 else "  "
                                    st.caption(f"  {marker} {ri+1}. `{rid}`")

                            # LLM 评估详情
                            if "faithfulness" in qr:
                                f_score = qr["faithfulness"].get("score", 0)
                                r_score = qr.get("relevance", {}).get("score", 0)
                                c_score = qr.get("completeness", {}).get("score", 0)
                                st.caption(f"**LLM评估:** 忠实度={f_score:.2f} | 相关性={r_score:.2f} | 完整性={c_score:.2f}")

                # 问题列表
                questions = r.get("questions", [])
                if questions and not query_results:
                    st.markdown(f"**测试问题 ({len(questions)}题):**")
                    for qi, q in enumerate(questions):
                        st.caption(f"  {qi+1}. {q}")
    else:
        st.info("暂无评测记录。运行一次评估后，结果会自动保存到这里。")


# 错误类型 → 根因分析 → 优化建议映射
ERROR_DIAGNOSIS = {
    "hallucination": {
        "root_cause": "LLM 生成阶段",
        "pipeline_stage": "generate",
        "diagnosis": "模型编造了上下文中不存在的信息，通常是 Prompt 约束不足或温度过高",
        "suggestions": [
            ("Answer Prompt", "在 system prompt 中明确要求「仅基于提供的上下文回答，不要编造信息」"),
            ("Temperature", "降低 temperature 参数（如 0.1 → 0.05），减少创造性"),
            ("上下文质量", "检查检索到的 chunk 是否包含噪音信息误导 LLM"),
            ("Rerank", "启用 Rerank 提升上下文相关性，减少噪音 chunk"),
        ],
        "eval_tip": "重点关注 Faithfulness 指标，运行 LLM-as-Judge 评估量化幻觉率"
    },
    "irrelevant": {
        "root_cause": "检索阶段",
        "pipeline_stage": "retrieval",
        "diagnosis": "检索到的上下文与问题不匹配，导致 LLM 基于无关内容生成答案",
        "suggestions": [
            ("Query 改写", "启用 enable_query_rewrite，让查询更精确匹配文档表述"),
            ("Embedding 模型", "检查 Embedding 模型对中文语义的理解能力，考虑换用更强模型"),
            ("BM25 权重", "增大 bm25_weight，加强关键词精确匹配"),
            ("chunk_size", "调整 chunk_size 确保语义完整性"),
        ],
        "eval_tip": "重点关注 Recall@5 和 MRR，检查检索结果中是否有相关内容"
    },
    "incomplete": {
        "root_cause": "检索 + 生成阶段",
        "pipeline_stage": "retrieval+generate",
        "diagnosis": "检索到了部分相关信息，但遗漏了关键内容，可能是召回不足或生成截断",
        "suggestions": [
            ("扩大召回", "增大 top_k_retrieval（如 20 → 50），扩大候选池"),
            ("MultiQuery", "启用 enable_multiquery，从不同角度召回更多候选"),
            ("chunk 切分", "检查 chunk_size 是否过小导致信息被拆散"),
            ("生成长度", "增大 max_tokens，确保答案有足够空间完整输出"),
            ("Prompt", "在 Prompt 中要求「全面回答，不要遗漏关键信息」"),
        ],
        "eval_tip": "重点关注 Completeness 和 Recall@5，对比参考答案检查遗漏项"
    },
    "factual_error": {
        "root_cause": "检索 + 生成阶段",
        "pipeline_stage": "retrieval+generate",
        "diagnosis": "答案中的数据或事实与原文不符，可能是检索到错误 chunk 或 LLM 误解",
        "suggestions": [
            ("Rerank", "启用 Rerank，确保最相关的 chunk 排在前面"),
            ("数值提取", "检查 table_serializer 是否正确序列化表格数据"),
            ("Prompt", "要求 LLM「引用原文中的具体数据，不要四舍五入或估算」"),
            ("chunk 质量", "检查相关 chunk 是否包含正确的原始数据"),
        ],
        "eval_tip": "重点关注 Faithfulness，对比原始文档验证数据准确性"
    },
    "outdated": {
        "root_cause": "知识库时效性",
        "pipeline_stage": "index",
        "diagnosis": "知识库中的文档不是最新版本，或未正确区分不同报告期的数据",
        "suggestions": [
            ("更新文档", "替换为最新版本的年报/季报 PDF"),
            ("增量索引", "使用 incremental_indexer 添加新文档，保留历史版本"),
            ("时间标注", "在 chunk metadata 中标注报告期，支持按时间筛选"),
        ],
        "eval_tip": "检查文档列表确认是否有最新版本"
    },
}


def _load_retrieval_log(log_id: str) -> Optional[Dict]:
    """加载检索日志文件"""
    if not log_id:
        return None
    log_path = Path(f"data/logs/{log_id}.json")
    if log_path.exists():
        with open(log_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def _analyze_bad_case_pipeline(fb: dict) -> dict:
    """分析单个 Bad Case 的管道各阶段"""
    analysis = {
        "error_type": fb.get("user_feedback", {}).get("error_type", ""),
        "has_retrieval_log": False,
        "retrieval_results": [],
        "query_rewrite": None,
        "multiquery_variants": [],
    }

    # 尝试加载关联的检索日志
    log_id = fb.get("retrieval_log_id", "")
    log_data = _load_retrieval_log(log_id)
    if log_data:
        analysis["has_retrieval_log"] = True
        for stage in log_data.get("stages", []):
            stage_name = stage.get("name", "")
            stage_data = stage.get("data", {})
            if stage_name == "query_rewrite":
                analysis["query_rewrite"] = {
                    "original": stage_data.get("original", ""),
                    "rewritten": stage_data.get("rewritten", ""),
                    "query_type": stage_data.get("query_type", ""),
                }
            elif stage_name == "multiquery":
                analysis["multiquery_variants"] = stage_data.get("variants", [])
            elif stage_name == "rerank":
                for r in stage_data.get("top_results", [])[:3]:
                    analysis["retrieval_results"].append({
                        "chunk_id": r.get("chunk_id", ""),
                        "score": r.get("score", 0),
                        "text_preview": r.get("text", "")[:100],
                    })

    # 从 feedback 中获取检索结果摘要
    if not analysis["retrieval_results"]:
        for r in (fb.get("retrieval_results") or [])[:3]:
            analysis["retrieval_results"].append({
                "chunk_id": r.get("chunk_id", ""),
                "score": r.get("score", 0),
                "page": r.get("page"),
            })

    return analysis


def render_monitor_page():
    """质量监控页面 - Bad Case 看板与根因分析"""
    st.markdown("""
    <div class="main-header">
        <h1>🔍 质量监控</h1>
        <p>Bad Case 收集 · 根因分析 · 优化建议</p>
    </div>
    """, unsafe_allow_html=True)

    from src.feedback_collector import FeedbackCollector
    collector = FeedbackCollector()

    # ===== 概览统计 =====
    analysis = collector.analyze_feedback()
    st.markdown("### 📈 概览")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("总反馈数", analysis["total"])
    with c2:
        rate = analysis.get("helpful_rate", 0)
        st.metric("好评率", f"{rate:.1%}")
    with c3:
        st.metric("差评数", analysis["unhelpful_count"])
    with c4:
        st.metric("Bad Case", analysis.get("bad_case_count", 0))

    if analysis["total"] == 0:
        st.info("暂无反馈数据。在问答页面对回答点击👍或👎开始收集反馈。")
        return

    bad_cases = collector.get_bad_cases()

    # ===== 错误模式分析 =====
    if bad_cases:
        st.markdown("---")
        st.markdown("### 🎯 错误模式分析")

        error_types = analysis.get("error_types", {})
        if error_types:
            # 按错误类型分析
            for etype, count in sorted(error_types.items(), key=lambda x: -x[1]):
                diag = ERROR_DIAGNOSIS.get(etype, {})
                error_label = ERROR_TYPE_OPTIONS.get(etype, etype)

                with st.expander(f"**{error_label}** — {count}次 | 根因: {diag.get('root_cause', '未知')}", expanded=count >= 2):
                    # 诊断
                    st.markdown(f"**诊断:** {diag.get('diagnosis', '暂无分析')}")

                    # 受影响的 Bad Case 列表
                    related_cases = [
                        fb for fb in bad_cases
                        if fb.get("user_feedback", {}).get("error_type") == etype
                    ]
                    if related_cases:
                        st.markdown(f"**相关案例 ({len(related_cases)}条):**")
                        for rc in related_cases[:3]:
                            q = rc.get("query", "")
                            st.caption(f"  · {q[:60]}")

                    # 优化建议
                    suggestions = diag.get("suggestions", [])
                    if suggestions:
                        st.markdown("**优化方向:**")
                        for param, desc in suggestions:
                            st.markdown(f"  - **{param}**: {desc}")

                    # 评估建议
                    eval_tip = diag.get("eval_tip", "")
                    if eval_tip:
                        st.info(f"📊 {eval_tip}")

    # ===== 按配置对比 =====
    by_config = analysis.get("by_config", {})
    if len(by_config) > 1:
        st.markdown("---")
        st.markdown("### ⚙️ 配置效果对比")
        config_rows = []
        for cfg, stats in by_config.items():
            helpful = stats.get("helpful", 0)
            total = stats["total"]
            config_rows.append({
                "配置": cfg.upper(),
                "反馈数": total,
                "好评数": helpful,
                "差评数": total - helpful,
                "好评率": f"{helpful / total:.1%}" if total > 0 else "N/A"
            })
        import pandas as pd
        st.dataframe(pd.DataFrame(config_rows), use_container_width=True, hide_index=True)

        # 建议
        best_cfg = max(by_config.items(), key=lambda x: x[1].get("helpful", 0) / x[1]["total"] if x[1]["total"] > 0 else 0)
        st.success(f"💡 当前好评率最高的配置: **{best_cfg[0].upper()}**（{best_cfg[1].get('helpful', 0) / best_cfg[1]['total']:.1%}），建议作为基准配置")

    # ===== Bad Case 列表（带管道分析） =====
    st.markdown("---")
    st.markdown("### 🔴 Bad Case 详情")

    # 筛选器
    fc1, fc2 = st.columns(2)
    with fc1:
        all_error_types = list(set(
            fb.get("user_feedback", {}).get("error_type", "unknown")
            for fb in bad_cases
            if fb.get("user_feedback", {}).get("error_type")
        ))
        all_error_types.insert(0, "全部")
        filter_type = st.selectbox("按错误类型筛选", all_error_types, key="monitor_filter_type")
    with fc2:
        all_configs = list(set(fb.get("config_name", "unknown") for fb in bad_cases))
        all_configs.insert(0, "全部")
        filter_config = st.selectbox("按配置筛选", all_configs, key="monitor_filter_config")

    # 应用筛选
    filtered = bad_cases
    if filter_type != "全部":
        filtered = [fb for fb in filtered if fb.get("user_feedback", {}).get("error_type") == filter_type]
    if filter_config != "全部":
        filtered = [fb for fb in filtered if fb.get("config_name") == filter_config]

    st.caption(f"共 {len(filtered)} 条 Bad Case")

    for i, fb in enumerate(filtered):
        query = fb.get("query", "")
        answer_raw = fb.get("answer", "")
        answer = answer_raw.get("final_answer", str(answer_raw)) if isinstance(answer_raw, dict) else str(answer_raw)
        feedback = fb.get("user_feedback", {})
        error_type = feedback.get("error_type", "")
        correct_answer = feedback.get("correct_answer", "")
        comment = fb.get("comment", "")
        config = fb.get("config_name", "")
        timestamp = fb.get("timestamp", "")[:16].replace("T", " ")

        error_label = ERROR_TYPE_OPTIONS.get(error_type, error_type or "未分类")
        diag = ERROR_DIAGNOSIS.get(error_type, {})

        with st.expander(f"**[{error_label}]** {query[:50]}... ({timestamp})", expanded=i < 2):
            # 基本信息
            st.markdown(f"**问题:** {query}")
            st.markdown(f"**系统回答:** {answer[:400]}{'...' if len(answer) > 400 else ''}")
            st.markdown(f"**错误类型:** {error_label} | **配置:** {config} | **时间:** {timestamp}")

            if correct_answer:
                st.markdown(f"**✅ 用户纠正:** {correct_answer}")
            if comment:
                st.markdown(f"**💬 评论:** {comment}")

            # 管道分析
            pipeline_analysis = _analyze_bad_case_pipeline(fb)

            if pipeline_analysis["has_retrieval_log"]:
                st.markdown("---")
                st.markdown("**🔍 检索链路分析:**")

                # Query 改写
                qr = pipeline_analysis.get("query_rewrite")
                if qr:
                    st.caption(f"  Query 改写: `{qr['original']}` → `{qr['rewritten']}` (类型: {qr['query_type']})")

                # MultiQuery
                variants = pipeline_analysis.get("multiquery_variants", [])
                if variants:
                    st.caption(f"  MultiQuery 扩展: {', '.join(variants[:3])}")

                # 检索结果
                results = pipeline_analysis.get("retrieval_results", [])
                if results:
                    st.markdown("  **Top 检索结果:**")
                    for j, r in enumerate(results[:3]):
                        page_info = f" (p.{r['page']})" if r.get("page") else ""
                        st.caption(f"    {j+1}. `{r['chunk_id']}` score={r['score']:.3f}{page_info}")

            # 诊断与建议
            if diag:
                st.markdown("---")
                st.markdown(f"**🎯 根因定位:** {diag.get('root_cause', '')} → {diag.get('pipeline_stage', '')}")
                st.markdown(f"**诊断:** {diag.get('diagnosis', '')}")

                suggestions = diag.get("suggestions", [])
                if suggestions:
                    st.markdown("**优化建议:**")
                    for param, desc in suggestions[:3]:
                        st.markdown(f"  - **{param}**: {desc}")

    # ===== 整体优化路线图 =====
    if bad_cases:
        st.markdown("---")
        st.markdown("### 🗺️ 优化路线图")

        # 统计各阶段的问题分布
        stage_counts = {"retrieval": 0, "generate": 0, "retrieval+generate": 0, "index": 0}
        for fb in bad_cases:
            etype = fb.get("user_feedback", {}).get("error_type", "")
            diag = ERROR_DIAGNOSIS.get(etype, {})
            stage = diag.get("pipeline_stage", "")
            if stage in stage_counts:
                stage_counts[stage] += 1

        total_bad = len(bad_cases)
        if total_bad > 0:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                pct = stage_counts["retrieval"] / total_bad
                st.metric("检索问题", f"{stage_counts['retrieval']}条", f"{pct:.0%}")
            with col2:
                pct = stage_counts["generate"] / total_bad
                st.metric("生成问题", f"{stage_counts['generate']}条", f"{pct:.0%}")
            with col3:
                pct = stage_counts["retrieval+generate"] / total_bad
                st.metric("检索+生成", f"{stage_counts['retrieval+generate']}条", f"{pct:.0%}")
            with col4:
                pct = stage_counts["index"] / total_bad
                st.metric("知识库问题", f"{stage_counts['index']}条", f"{pct:.0%}")

            # 优先级建议
            dominant_stage = max(stage_counts.items(), key=lambda x: x[1])
            if dominant_stage[1] > 0:
                stage_advice = {
                    "retrieval": "🔴 **优先优化检索阶段**: 检查 chunk_size、BM25 权重、Embedding 模型质量",
                    "generate": "🔴 **优先优化生成阶段**: 优化 Answer Prompt、降低温度、加强上下文约束",
                    "retrieval+generate": "🔴 **检索和生成都需要优化**: 建议先优化检索（提升 Recall），再优化生成（提升 Faithfulness）",
                    "index": "🔴 **知识库需要更新**: 检查文档版本、补充缺失文档、更新过时数据",
                }
                st.warning(stage_advice.get(dominant_stage[0], ""))

    # ===== 导出与行动 =====
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📥 导出 Bad Case 为 JSON"):
            output_path = Path("data/feedback/bad_cases_export.json")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(filtered, f, ensure_ascii=False, indent=2)
            st.success(f"已导出 {len(filtered)} 条 Bad Case 到 {output_path}")
    with col2:
        if st.button("📊 将 Bad Case 加入评测集"):
            # 将有纠正答案的 bad case 转为评测问题
            added = 0
            eval_path = Path("data/eval_questions.json")
            if eval_path.exists():
                with open(eval_path, 'r', encoding='utf-8') as f:
                    eval_data = json.load(f)

                for fb in bad_cases:
                    q = fb.get("query", "")
                    correct = fb.get("user_feedback", {}).get("correct_answer", "")
                    if q and correct and q not in eval_data.get("questions", []):
                        eval_data.setdefault("questions", []).append(q)
                        eval_data.setdefault("ground_truth", {})[q] = {
                            "answer": correct,
                            "context": ""
                        }
                        etype = fb.get("user_feedback", {}).get("error_type", "")
                        eval_data.setdefault("question_categories", {})[q] = "FACT"
                        added += 1

                if added > 0:
                    with open(eval_path, 'w', encoding='utf-8') as f:
                        json.dump(eval_data, f, ensure_ascii=False, indent=2)
                    st.success(f"已将 {added} 条 Bad Case 加入评测集，下次评估会覆盖这些问题")
                else:
                    st.info("没有新的可加入的 Bad Case（需要有用户纠正答案）")


def main():
    init_session_state()
    render_sidebar()

    if st.session_state.current_view == "qa":
        render_qa_page()
    elif st.session_state.current_view == "monitor":
        render_monitor_page()
    else:
        render_eval_page()


if __name__ == "__main__":
    main()