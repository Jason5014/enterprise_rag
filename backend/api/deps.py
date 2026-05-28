"""FastAPI 依赖注入 — 当前用户、存储实例"""
import sys
from pathlib import Path
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# 确保项目根目录在 sys.path
ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import DB_PATH, DATA_DIR, ADMIN_USERNAME, ADMIN_PASSWORD
from backend.core.security import decode_token, hash_password
from src.storage.local_file import LocalFileStorage
from src.storage.sqlite_meta import SQLiteMetadataStore
from src.kb_manager import KBManager

_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# 单例存储实例
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_file_storage() -> LocalFileStorage:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return LocalFileStorage(str(DATA_DIR))


@lru_cache(maxsize=1)
def get_metadata_store() -> SQLiteMetadataStore:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    store = SQLiteMetadataStore(DB_PATH)
    _ensure_admin(store)
    _ensure_builtin_kb(store)
    return store


@lru_cache(maxsize=1)
def get_kb_manager() -> KBManager:
    return KBManager(get_file_storage(), get_metadata_store())


def _ensure_admin(store: SQLiteMetadataStore) -> None:
    """首次启动时创建 admin 账号"""
    if store.get_user_by_username(ADMIN_USERNAME) is None:
        store.create_user(
            username=ADMIN_USERNAME,
            email=None,
            password_hash=hash_password(ADMIN_PASSWORD),
            role="admin",
        )


# 内置 KB 的固定 ID（与 data/chunked/ 对应）
BUILTIN_KB_ID = "builtin-default"


def _ensure_builtin_kb(store: SQLiteMetadataStore) -> None:
    """首次启动时，若 data/chunked/ 有已构建的索引，自动注册为内置知识库。
    这样用户无需跑 process-reports CLI，直接在 UI 里就能看到并使用它。
    """
    if store.get_kb(BUILTIN_KB_ID) is not None:
        return  # 已注册，跳过

    builtin_chunked = ROOT / "data" / "chunked"
    if not (builtin_chunked / "chunks.json").exists():
        return  # 索引还不存在，跳过（等用户跑完 process-reports 再注册）

    # 统计 chunk 数量
    import json as _json
    try:
        data = _json.loads((builtin_chunked / "chunks.json").read_text(encoding="utf-8"))
        chunk_count = len(data.get("chunks", []))
    except Exception:
        chunk_count = 0

    # 统计 PDF 数量
    raw_dir = ROOT / "data" / "pdf_reports"
    doc_count = len(list(raw_dir.glob("*.pdf"))) if raw_dir.exists() else 0

    store.create_kb(
        kb_id=BUILTIN_KB_ID,
        name="内置知识库（中芯国际研报）",
        description="由 data/pdf_reports/ 目录中的研报自动构建，使用 data/chunked/ 索引",
        config_name="base",
        status="ready",
        index_dir=str(builtin_chunked),
    )
    store.update_kb(BUILTIN_KB_ID, doc_count=doc_count, chunk_count=chunk_count)
    import logging as _logging
    _logging.getLogger(__name__).info(
        "已自动注册内置 KB: %d 文件 / %d chunks", doc_count, chunk_count
    )


# ---------------------------------------------------------------------------
# 认证依赖
# ---------------------------------------------------------------------------

def get_current_user(
    request=None,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    meta: SQLiteMetadataStore = Depends(get_metadata_store),
):
    # 优先从 Authorization Header 取 token；SSE 场景也支持 query param ?token=...
    raw_token = None
    if credentials:
        raw_token = credentials.credentials
    elif request is not None:
        raw_token = request.query_params.get("token")

    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="未提供认证凭据")
    payload = decode_token(raw_token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token 无效或已过期")
    user = meta.get_user_by_id(payload.get("sub", ""))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="用户不存在或已禁用")
    return user


def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="需要管理员权限")
    return user
