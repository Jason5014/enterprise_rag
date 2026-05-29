"""系统状态路由"""
import logging
import sys
from pathlib import Path

from fastapi import APIRouter, Depends

from backend.api.deps import get_current_user

ROOT = Path(__file__).parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/status")
def system_status(user=Depends(get_current_user)):
    """返回系统状态：文档数、分块数、向量库状态"""
    data_dir = ROOT / "data"

    # 统计 PDF
    pdf_dir = data_dir / "pdf_reports"
    pdf_count = len(list(pdf_dir.glob("*.pdf"))) if pdf_dir.exists() else 0

    # 统计分块
    chunk_count = 0
    chunked_file = data_dir / "chunked" / "chunks.json"
    if chunked_file.exists():
        try:
            import json
            with open(chunked_file, "r", encoding="utf-8") as f:
                d = json.load(f)
            chunk_count = len(d.get("chunks", []))
        except Exception:
            pass

    # 向量库状态
    vector_db_dir = data_dir / "chunked" / "vector_db"
    vector_ready = False
    vector_file_count = 0
    if vector_db_dir.exists():
        for f in vector_db_dir.rglob("*"):
            if f.is_file() and f.suffix in [".json", ".index", ".faiss", ".npy"]:
                vector_file_count += 1
        vector_ready = vector_file_count > 0

    # 知识库数量（SQLite 或 JSON）
    kb_count = 0
    try:
        from backend.api.deps import get_kb_manager
        # 不依赖 request，直接实例化
        from src.kb_manager import KBManager
        mgr = KBManager()
        kb_count = len(mgr.list_kbs())
    except Exception:
        pass

    return {
        "pdf_count": pdf_count,
        "chunk_count": chunk_count,
        "vector_ready": vector_ready,
        "vector_file_count": vector_file_count,
        "kb_count": kb_count,
    }
