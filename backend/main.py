"""FastAPI 入口 — uvicorn backend.main:app --reload"""
import sys
from pathlib import Path

# 确保项目根目录在 sys.path，使 src/ config/ 可直接 import
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import CORS_ORIGINS
from backend.api.routers import auth, kb, qa, eval, monitor, config, system

app = FastAPI(title="企业知识库 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,    prefix="/api/auth",    tags=["认证"])
app.include_router(kb.router,      prefix="/api/kb",      tags=["知识库"])
app.include_router(qa.router,      prefix="/api/qa",      tags=["问答"])
app.include_router(eval.router,    prefix="/api/eval",    tags=["评估"])
app.include_router(monitor.router, prefix="/api/monitor", tags=["监控"])
app.include_router(config.router,  prefix="/api/config",  tags=["配置"])
app.include_router(system.router,  prefix="/api/system",  tags=["系统"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
