# 企业 RAG 知识库系统

基于 RAG Challenge 获奖方案设计理念的企业级知识库问答系统，支持多知识库管理、流式问答、评估监控。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue3 + Element Plus + Vite + Pinia |
| 后端 | FastAPI + SSE + JWT 认证 |
| 检索 | FAISS 向量检索 + BM25（jieba 中文分词）混合 RRF 融合 |
| 重排 | LLM Listwise 重排 / Jina Reranker |
| 解析 | MinerU API（PDF → Markdown） |
| 存储 | SQLite（元数据）+ 本地 FS（文件/索引）→ 预留 PostgreSQL / MinIO 迁移 |
| LLM | 阿里云 DashScope（qwen-turbo） |

## 核心功能

- **多知识库管理** — 创建 / 上传 / 解析 / 索引，全程可视化进度
- **流式问答** — SSE 逐 token 推送，含推理过程折叠展示
- **混合检索** — 向量 + BM25，RRF / 加权融合可切换
- **父子 Chunk** — Parent Document Retrieval 改善上下文完整性
- **MultiQuery + Query Rewrite** — 查询扩展提升召回
- **LLM 重排** — Listwise 模式，一次调用完成多候选排序
- **评估体系** — Hit@K / Recall@K / MRR / NDCG，SSE 实时进度
- **质量监控** — 👍/👎 反馈收集，Bad Case 看板，JSONL 导出
- **存储抽象层** — `FileStorage` / `MetadataStore` 接口，换 MinIO / PostgreSQL 只需换实现类

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少填写 DASHSCOPE_API_KEY
```

### 2. 安装依赖

```bash
make install          # 同时安装 Python 依赖 + Node.js 依赖
```

> 如果没有 make，手动执行：
> ```bash
> pip install -r requirements.txt
> cd frontend && npm install
> ```

### 3. 启动服务

```bash
# 终端 1 — 后端 API（:8000）
make backend

# 终端 2 — 前端 dev server（:5173）
make frontend
```

打开 http://localhost:5173，默认账号 **admin / admin123**。

> 装有 `tmux` 可用 `make dev` 一键并行启动。

### 4. 常用命令

```bash
make build     # 生产构建前端（frontend/dist/）
make test      # 后端单元测试
make lint      # 前端 TypeScript 类型检查
make clean     # 清理构建产物
make help      # 查看所有 make 命令
```

### 5. CLI（旧版，仍可用）

```bash
python main.py process-reports   # 解析 + 索引内置数据
python main.py query             # 交互式问答
python main.py list-configs      # 查看所有预设配置
python main.py ui                # 启动 Streamlit UI（过渡期保留）
```

## 目录结构

```
enterprise_rag/
├── backend/                    FastAPI 后端
│   ├── main.py                 入口（uvicorn backend.main:app）
│   ├── core/
│   │   ├── config.py           环境变量配置
│   │   └── security.py         JWT 签发/验证 + bcrypt
│   └── api/
│       ├── deps.py             依赖注入（存储单例 + 认证守卫）
│       ├── schemas/            Pydantic 请求/响应模型
│       └── routers/
│           ├── auth.py         登录 / 注册 / 当前用户
│           ├── kb.py           知识库 CRUD + 文件管理 + 任务
│           ├── qa.py           同步问答 + SSE 流式 + 反馈
│           ├── eval.py         SSE 进度评估 + 历史
│           └── monitor.py      统计 + Bad Case + 导出
│
├── frontend/                   Vue3 前端（Vite + Element Plus）
│   └── src/
│       ├── views/
│       │   ├── LoginView.vue
│       │   ├── QAView.vue          流式问答（SSE EventSource）
│       │   ├── KBListView.vue      知识库列表
│       │   ├── KBDetailView.vue    文件 / 任务 / 配置三 Tab
│       │   ├── EvalView.vue        SSE 进度评估
│       │   └── MonitorView.vue     质量监控看板
│       ├── stores/             Pinia（auth / kb / qa）
│       ├── api/                axios 封装 + http 拦截器
│       └── router/             路由守卫（未登录跳 /login）
│
├── src/                        核心业务模块
│   ├── storage/
│   │   ├── base.py             抽象接口（FileStorage / MetadataStore）
│   │   ├── local_file.py       LocalFileStorage 实现
│   │   └── sqlite_meta.py      SQLiteMetadataStore 实现
│   ├── kb_manager.py           知识库管理（协调存储 + pipeline）
│   ├── pipeline.py             RAG 主流程（含 stream_answer）
│   ├── answer_generator.py     答案生成（含 stream_generate）
│   ├── retriever.py            混合检索（FAISS + BM25 + RRF）
│   ├── reranker.py             LLM Listwise 重排 / Jina
│   ├── multi_query.py          MultiQuery + Query Rewrite
│   └── ...
│
├── config/                     配置层
│   ├── presets.py              base / fast / precision / full
│   └── retrieval_config.py     检索参数（index_dir / fusion_method / ...）
│
├── data/                       数据目录（git 忽略大文件）
│   ├── kb.db                   SQLite 元数据（git 忽略）
│   ├── kb/{kb_id}/             各知识库数据（git 忽略）
│   ├── eval_results/           评测历史（保留）
│   └── feedback/               用户反馈（保留）
│
├── ui/                         Streamlit UI（过渡期保留）
├── .env.example                环境变量模板
├── Makefile                    一键启动 / 构建 / 测试
├── requirements.txt            Python 依赖
└── ARCHITECTURE.md             架构设计文档
```

## 配置预设

| 预设 | 特点 | 适用场景 |
|------|------|---------|
| `base` | 仅混合检索，无重排/MultiQuery | 快速验证 |
| `fast` | 关闭父子 Chunk 和重排 | 速度优先 |
| `precision` | 全功能，top_k=30，5 个 MultiQuery | 精度优先 |
| `full` | 全功能 + 增量索引 + 详细日志 | 生产推荐 |

## 存储演进路径

| 组件 | 当前 | 演进目标 | 切换条件 |
|------|------|---------|---------|
| 元数据 | SQLite | PostgreSQL | 多实例 / 高并发写 |
| 文件存储 | 本地 FS | MinIO / S3 | 多节点 / 容器化 |
| 向量索引 | FAISS | Qdrant / Milvus | 单 KB > 100 万向量 |
| 关键词搜索 | BM25 | Elasticsearch | 多 KB 联合搜索 |

切换任意一层只需实现对应抽象接口的新类，在 `deps.py` 替换注入实例，业务逻辑不变。

## API 文档

后端启动后访问 http://localhost:8000/docs（Swagger UI）。

## License

MIT
