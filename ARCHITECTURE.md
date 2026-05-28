# 企业RAG知识库 — 重构架构文档

## 目标架构

```
┌─────────────────────────────────────────────┐
│      Vue3 + Element Plus (前端)              │
│   Vue Router / Pinia / Axios / EventSource  │
└──────────────────┬──────────────────────────┘
                   │ HTTP REST / SSE
┌──────────────────▼──────────────────────────┐
│         FastAPI 后端 (backend/)              │
│  /api/auth  /api/kb  /api/qa  /api/eval     │
└──────────────────┬──────────────────────────┘
                   │ Python 调用
┌──────────────────▼──────────────────────────┐
│       业务逻辑层 (src/) — 现有模块不动         │
│  pipeline / kb_manager / evaluator / ...    │
└──────┬───────────┬────────────┬─────────────┘
       │           │            │
  ┌────▼───┐  ┌────▼────┐  ┌───▼───────────┐
  │MetaDB  │  │FileStore│  │Vector + BM25  │
  │SQLite  │  │本地 FS  │  │FAISS+rank_bm25│
  │→Postgres  │→MinIO   │  │→Qdrant/Milvus │
  └────────┘  └─────────┘  └───────────────┘
```

---

## 目录结构

```
enterprise_rag/
├── backend/                    FastAPI 应用
│   ├── main.py                 入口，挂载所有 router + CORS
│   ├── api/
│   │   ├── routers/
│   │   │   ├── auth.py         登录 / 注册 / 当前用户
│   │   │   ├── kb.py           知识库 CRUD + 文件 + 任务
│   │   │   ├── qa.py           问答（同步 + SSE 流式）
│   │   │   ├── eval.py         评估运行 + 历史
│   │   │   └── monitor.py      反馈 + Bad Case
│   │   ├── schemas/            Pydantic 请求/响应模型
│   │   │   ├── auth.py
│   │   │   ├── kb.py
│   │   │   └── qa.py
│   │   └── deps.py             依赖注入（当前用户、DB 实例）
│   └── core/
│       ├── config.py           从 .env 读取后端配置
│       └── security.py         JWT 签发/验证、密码 hash
│
├── frontend/                   Vue3 应用
│   ├── src/
│   │   ├── views/
│   │   │   ├── QAView.vue          /qa       问答助手
│   │   │   ├── KBListView.vue      /kb       知识库列表
│   │   │   ├── KBDetailView.vue    /kb/:id   知识库详情
│   │   │   ├── EvalView.vue        /eval     评估测试
│   │   │   └── MonitorView.vue     /monitor  质量监控
│   │   ├── components/
│   │   │   ├── chat/
│   │   │   │   ├── ChatWindow.vue      对话主区（含流式）
│   │   │   │   ├── MessageItem.vue     单条消息（Markdown渲染）
│   │   │   │   └── ThinkingProcess.vue 检索过程折叠展示
│   │   │   ├── kb/
│   │   │   │   ├── KBCard.vue          知识库卡片
│   │   │   │   ├── FileUploader.vue    文件上传（拖拽+进度）
│   │   │   │   └── ProcessProgress.vue 处理进度（轮询job状态）
│   │   │   └── eval/
│   │   │       ├── MetricsPanel.vue    指标卡片
│   │   │       └── ResultTable.vue     评估结果表格
│   │   ├── stores/             Pinia 状态管理
│   │   │   ├── auth.ts             用户登录状态
│   │   │   ├── kb.ts               KB 列表 + 当前激活 KB
│   │   │   └── qa.ts               对话历史 + 配置
│   │   ├── api/                axios 封装
│   │   │   ├── http.ts             axios 实例 + 拦截器（token注入）
│   │   │   ├── auth.ts
│   │   │   ├── kb.ts
│   │   │   └── qa.ts
│   │   └── router/
│   │       └── index.ts            路由守卫（未登录跳登录页）
│   ├── package.json
│   └── vite.config.ts              proxy: /api → http://localhost:8000
│
├── src/                        现有业务模块（基本不动）
│   ├── storage/                新增：存储抽象层
│   │   ├── base.py             抽象接口（FileStorage / MetadataStore）
│   │   ├── local_file.py       LocalFileStorage 实现
│   │   └── sqlite_meta.py      SQLiteMetadataStore 实现
│   ├── kb_manager.py           新增：KB管理（使用抽象层）
│   ├── pipeline.py             不变（已支持 index_dir 参数）
│   ├── answer_generator.py     新增 stream_generate() 方法
│   └── ...其余不变
│
├── config/                     不变
├── data/
│   ├── kb.db                   新增：SQLite 元数据
│   ├── kb/                     新增：各 KB 数据
│   │   └── {kb_id}/
│   │       ├── raw/            上传的原始文件
│   │       ├── parsed/         MinerU 解析结果
│   │       └── chunked/        索引文件
│   └── chunked/                保留（内置默认 KB）
│
└── ui/                         过渡期保留，最终废弃
    └── app.py
```

---

## 存储抽象层接口

所有存储访问通过抽象接口，不直接操作文件系统，确保将来替换实现时业务逻辑不变。

```python
# src/storage/base.py

class FileStorage(ABC):
    """文件存储接口 — LocalFS 现在 / MinIO·S3 将来"""
    def save(self, kb_id, category, filename, content: bytes) -> str: ...
    def load(self, storage_path: str) -> bytes: ...
    def delete(self, storage_path: str) -> bool: ...
    def list_files(self, kb_id, category) -> List[FileInfo]: ...
    def get_local_path(self, storage_path: str) -> Path: ...
    # get_local_path: MinIO 实现时先下载到临时目录，供 FAISS 等需要文件路径的工具使用

class MetadataStore(ABC):
    """元数据存储接口 — SQLite 现在 / PostgreSQL 将来"""
    # KB
    def create_kb(self, name, description, config_name) -> str: ...
    def get_kb(self, kb_id) -> Optional[KBRecord]: ...
    def list_kbs(self, user_id=None) -> List[KBRecord]: ...
    def update_kb(self, kb_id, **fields): ...
    def delete_kb(self, kb_id): ...
    # Documents
    def create_document(self, kb_id, filename, file_type, size) -> str: ...
    def update_document(self, doc_id, **fields): ...
    def list_documents(self, kb_id) -> List[DocRecord]: ...
    def delete_document(self, doc_id): ...
    # Jobs
    def create_job(self, kb_id, job_type) -> str: ...
    def update_job(self, job_id, **fields): ...
    def list_jobs(self, kb_id, limit=10) -> List[JobRecord]: ...
    # Users
    def create_user(self, username, email, password_hash) -> str: ...
    def get_user_by_username(self, username) -> Optional[UserRecord]: ...
    def get_user_by_id(self, user_id) -> Optional[UserRecord]: ...
```

---

## 数据库表结构（SQLite）

```sql
-- 用户表
CREATE TABLE users (
    user_id      TEXT PRIMARY KEY,
    username     TEXT UNIQUE NOT NULL,
    email        TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    role         TEXT DEFAULT 'user',   -- admin / user
    is_active    INTEGER DEFAULT 1,
    created_at   TEXT NOT NULL
);

-- 知识库表
CREATE TABLE knowledge_bases (
    kb_id       TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    config_name TEXT DEFAULT 'base',
    status      TEXT DEFAULT 'empty',  -- empty/processing/ready/error
    doc_count   INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    owner_id    TEXT REFERENCES users(user_id),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 文档表
CREATE TABLE documents (
    doc_id       TEXT PRIMARY KEY,
    kb_id        TEXT NOT NULL REFERENCES knowledge_bases(kb_id) ON DELETE CASCADE,
    filename     TEXT NOT NULL,
    file_type    TEXT,                  -- pdf / json
    file_size    INTEGER DEFAULT 0,
    storage_path TEXT,                 -- 抽象存储路径（将来换MinIO时路径格式变，逻辑不变）
    upload_time  TEXT NOT NULL,
    parse_status TEXT DEFAULT 'pending', -- pending/processing/done/failed
    parse_error  TEXT,
    chunk_count  INTEGER DEFAULT 0
);

-- 处理任务表
CREATE TABLE processing_jobs (
    job_id      TEXT PRIMARY KEY,
    kb_id       TEXT NOT NULL REFERENCES knowledge_bases(kb_id),
    job_type    TEXT,                  -- parse / index / full
    status      TEXT DEFAULT 'pending', -- pending/running/done/failed
    progress    REAL DEFAULT 0.0,
    stage_msg   TEXT,
    started_at  TEXT,
    finished_at TEXT,
    error_msg   TEXT,
    stats_json  TEXT                   -- {"chunk_count": 100, "doc_count": 3}
);
```

---

## API 路由

```
认证
  POST /api/auth/register     注册
  POST /api/auth/login        登录，返回 JWT token
  GET  /api/auth/me           当前用户信息

知识库
  GET    /api/kb/                KB 列表
  POST   /api/kb/                创建 KB
  GET    /api/kb/{kb_id}         KB 详情 + 统计
  PATCH  /api/kb/{kb_id}         更新名称/描述
  DELETE /api/kb/{kb_id}         删除（需 confirm=true 参数）

文件管理
  POST   /api/kb/{kb_id}/files              上传文件（multipart）
  GET    /api/kb/{kb_id}/files              文件列表
  DELETE /api/kb/{kb_id}/files/{doc_id}     删除文件

处理任务
  POST /api/kb/{kb_id}/parse        触发 PDF 解析，返回 job_id
  POST /api/kb/{kb_id}/index        触发构建索引，返回 job_id
  GET  /api/kb/{kb_id}/jobs         任务历史列表
  GET  /api/jobs/{job_id}/status    轮询任务状态（前端每 2s 轮询）

问答
  POST /api/qa/ask                  同步问答（等完整答案）
  GET  /api/qa/stream               SSE 流式问答（逐 token）
    query params: q, kb_id, config
  POST /api/qa/feedback             提交反馈（👍/👎）
  DELETE /api/qa/history            清空对话历史

评估
  POST /api/eval/run                SSE 流式运行（实时进度）
  GET  /api/eval/history            历史评估记录

监控
  GET  /api/monitor/stats           概览统计
  GET  /api/monitor/bad-cases       Bad Case 列表（支持筛选）
  POST /api/monitor/export          导出 Bad Case
```

---

## 前端路由

```
/login              登录页
/                   → redirect /qa
/qa                 问答助手（流式对话）
/kb                 知识库列表
/kb/:id             知识库详情（Tab: 文件管理 / 处理状态 / 配置）
/eval               评估测试
/monitor            质量监控
```

---

## DashScope 流式输出

`Generation.call()` 支持 `stream=True` + `incremental_output=True`，返回 Generator：

```python
# src/answer_generator.py 新增方法
def stream_generate(self, query, context, history=None):
    """生成器函数，逐 token yield"""
    response = Generation.call(
        model=self.model,
        messages=messages,
        api_key=api_key,
        stream=True,
        incremental_output=True
    )
    for chunk in response:
        if chunk.status_code == 200:
            token = chunk.output.get("text", "")
            if token:
                yield token

# backend/api/routers/qa.py
from sse_starlette.sse import EventSourceResponse

@router.get("/stream")
async def stream_answer(q: str, kb_id: str = None, current_user = Depends(get_current_user)):
    pipeline = get_pipeline_for_kb(kb_id)
    async def generator():
        for token in pipeline.stream_answer(q):
            yield {"data": token}
        yield {"data": "[DONE]"}
    return EventSourceResponse(generator())
```

---

## 演进路径

| 存储组件 | 当前实现 | 演进目标 | 切换条件 |
|---------|---------|---------|---------|
| 元数据 | SQLite | PostgreSQL | 多实例部署 / 高并发写 |
| 文件存储 | 本地 FS | MinIO / S3 | 多节点 / 容器化部署 |
| 向量索引 | FAISS | Qdrant / Milvus | 单 KB > 100万向量 / 需要实时更新 |
| 关键词搜索 | rank_bm25 | Elasticsearch | 多 KB 联合搜索 / 全文检索需求 |
| 认证会话 | JWT（无状态） | Redis + JWT | 需要强制下线 / Token 黑名单 |

切换任意一层时，只需实现对应抽象接口的新类，在 `deps.py` 中替换注入实例，业务逻辑不变。
