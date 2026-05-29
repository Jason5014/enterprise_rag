# CLAUDE.md - 企业RAG知识库项目

## 项目概述
这是一个企业RAG知识库系统，用于处理中芯国际等企业的PDF年报、季报、研报等文档，实现智能问答。

---

## 快速启动

### 1. 配置环境变量
```bash
cp .env.example .env      # 复制模板
# 编辑 .env，至少填写 DASHSCOPE_API_KEY
```

### 2. 安装依赖（首次）
```bash
make install              # 同时安装 Python 依赖 + Node.js 依赖
# 或分开安装：
make install-python       # pip install -r requirements.txt
make install-node         # cd frontend && npm install
```

### 3. 启动服务（两个终端）

**终端 1 — 后端（FastAPI :8900）**
```bash
make backend
# 等价于：python -m uvicorn backend.main:app --reload --port 8900
```

**终端 2 — 前端（Vue3 dev server :5173）**
```bash
make frontend
# 等价于：cd frontend && npm run dev
```

访问 http://localhost:5173，默认账号 `admin / admin123`。

> **如果装有 tmux**，可以用 `make dev` 一键在两个窗口中并行启动。

### 4. 其他常用命令
| 命令 | 作用 |
|------|------|
| `make build` | 生产构建前端（输出 `frontend/dist/`） |
| `make test` | 后端单元测试（`pytest tests/`） |
| `make lint` | 前端 TypeScript 类型检查 |
| `make clean` | 清理构建产物和 `__pycache__` |
| `make help` | 查看所有命令 |

### 5. 自定义端口
```bash
make backend  BACKEND_PORT=9000
make frontend FRONTEND_PORT=3000
```

### 6. API 文档
后端启动后访问 http://localhost:8900/docs（Swagger UI）。

---

## 关键原则

### 1. 禁止硬编码 - Query分类纯LLM实现，响应解析从YAML读取标记

**Query路由** (`src/query_router.py`)：
- `QueryRouter.classify()` 纯LLM调用分类，无关键词匹配Fallback
- System prompt 从 `QueryType` 枚举动态生成
- 响应解析只提取"类型:"、"置信度:"、"理由:"三个字段

**配置**：`config/query_types.yaml`
- `response_parsing`: 响应解析标记（analysis_markers/answer_markers/stop_markers）

**AnswerGenerator响应解析**：
- 从 `AnswerConfig` 读取 markers（来自YAML）
- 解析LLM输出：提取推理过程和最终答案

### 2. Query类型路由
`QueryRouter` 根据问题类型选择不同的Prompt模板：
- `NAME`: 名称型问题 → `build_name_prompt`
- `NUMBER`: 数值型问题 → `build_number_prompt`
- `BOOLEAN`: 是否型问题 → `build_boolean_prompt`
- `NAMES`: 列表型问题 → `build_names_prompt`
- `COMPARATIVE`: 比较型问题 → `build_comparative_prompt`
- `UNKNOWN`: 默认处理

### 3. 响应解析
`AnswerGenerator._parse_response()` 解析LLM输出：
- 推理过程（step_by_step_analysis）：从 `analysis_markers` 标记开始收集
- 最终答案（final_answer）：从 `answer_markers` 标记开始收集，遇到 `stop_markers` 停止

所有标记从 `AnswerConfig.analysis_markers` 等字段读取。

### 4. 配置修改流程
如果要修改任何业务逻辑（如问题分类规则、响应解析标记）：
1. 修改对应的 `config/` 下的配置类
2. 确保代码从配置对象读取，而不是写死
3. 验证修改效果

## 技术栈
- Python 3.11+
- Streamlit (Web UI)
- DashScope (阿里云LLM)
- FAISS (向量检索)
- BM25 (关键词检索)
- Jina AI Reranker

## 日志架构

### 集中式日志系统
- **配置**: `config/logging_config.py` — `LogConfig` 数据类
- **初始化**: `src/logging_setup.py` — `init_logging()` 幂等初始化
- **输出**:
  - 控制台 (stderr): 彩色格式 `[LEVEL] module - message`
  - 文件: `data/logs/app.log` (10MB x 5 旋转)
  - JSON: `data/logs/app.jsonl` (20MB x 3 旋转)

### 使用方式
```python
import logging
logger = logging.getLogger(__name__)

logger.debug("调试信息: %s", value)
logger.info("状态信息: %s", value)
logger.warning("警告信息: %s", value)
logger.error("错误信息: %s", value, exc_info=True)
```

### 日志级别
- `DEBUG`: 详细调试信息（文件）
- `INFO`: 一般状态信息（控制台+文件）
- `WARNING`: 警告信息
- `ERROR`: 错误信息（含堆栈）

### 初始化入口
- `main.py`: CLI 入口调用 `init_logging(LogConfig())`
- `ui/app.py`: Streamlit UI 调用 `init_logging(LogConfig(console_level="WARNING"))`

### 与 RetrievalLogger 的关系
- `RetrievalLogger` 保留不变（per-query 结构化 JSON 日志）
- 其内部 `print()` 已替换为标准 logger 调用

## 评估系统

### 检索评估指标
- **Hit@K**（推荐）: Top-K 中是否至少命中一个预期 chunk（1或0）。最直观的检索质量指标。
- **Recall@K**: Top-K 命中数 / 预期总数。注意：预期 chunk 越多，Recall@1 天然越低（如 5 个预期 chunk 最高 20%），需结合 Hit@K 看。
- **MRR**: 第一个正确结果的排名倒数。越高说明答案越靠前。
- **NDCG@5**: 考虑排序位置的综合质量指标。

### LLM-as-Judge 评估
- **评估器**: `src/evaluator.py` — `LLMJudgeEvaluator` 类
- **配置**: `config/eval_config.py` — `EvalConfig` 数据类（含可配置 Prompt 模板）
- **CLI**: `eval_llm_judge.py` — 独立评估脚本
- **UI集成**: `ui/app.py` 评估页面有"启用 LLM-as-Judge 评估"复选框

### 评估指标
- **Hit@1/3/5**: Top-K 中是否至少命中一个预期 chunk（推荐，最直观）
- **Recall@5**: Top-5 命中数占预期总数比例（核心检索质量指标）
- **Faithfulness（忠实度）**: 答案是否基于检索上下文，无幻觉
- **Relevance（相关性）**: 答案是否回答了问题
- **Completeness（完整性）**: 答案是否完整（需参考答案）

### 评测历史
- **管理器**: `src/eval_history.py` — `EvalHistory` 类
- **存储**: `data/eval_results/eval_history.jsonl`（JSONL 格式，逐条追加）
- **功能**: 每次评测自动保存，支持历史对比、趋势图、配置快照
- **UI**: 评测页面底部 "📊 评测历史" 区域

### 质量监控（Bad Case）
- **反馈收集**: `src/feedback_collector.py` — `FeedbackCollector` 类
- **存储**: `data/feedback/feedback.jsonl`
- **功能**:
  - 👎 详细反馈：错误类型（幻觉/不相关/不完整/事实错误）、纠正答案、评论
  - 自动检测潜在 Bad Case（兜底话术、无引用、推理过短）
  - Bad Case 看板：按错误类型筛选、根因分析、优化建议
- **UI**: 侧边栏 "🔍 质量监控" 页面

### 优化反馈
- **优化器**: `src/optimizer.py` — `RAGOptimizer` 类
- **文档**: `docs/optimization_guide.md`, `docs/rag_metrics.md`

## 目录结构
```
enterprise_rag/
├── config/          # 配置模块
│   ├── logging_config.py  # 日志配置
│   ├── eval_config.py     # 评估配置（含Prompt模板）
│   └── ...
├── src/             # 核心逻辑
│   ├── logging_setup.py   # 日志初始化
│   ├── evaluator.py       # 评估器（含LLMJudgeEvaluator + Hit@K）
│   ├── eval_history.py    # 评测历史管理
│   ├── feedback_collector.py  # 反馈收集（Bad Case）
│   ├── optimizer.py       # 优化反馈
│   ├── pipeline.py        # RAG主流程
│   ├── retriever.py       # 混合检索
│   ├── reranker.py        # 重排
│   ├── query_router.py    # 查询分类
│   └── answer_generator.py  # 答案生成
├── ui/
│   └── app.py           # Streamlit界面（问答+评估+质量监控）
├── eval_llm_judge.py  # LLM评估CLI脚本
├── data/
│   ├── eval_questions.json  # 评测问题集（含ground_truth）
│   ├── eval_results/        # 评测结果（eval_history.jsonl）
│   ├── feedback/            # 用户反馈（feedback.jsonl）
│   └── logs/                # 日志目录
└── main.py         # CLI入口
```