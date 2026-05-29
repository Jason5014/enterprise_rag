from typing import List
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query

from backend.api.deps import get_kb_manager, get_current_user

ROOT = Path(__file__).parent.parent.parent.parent
from backend.api.schemas.kb import (
    KBCreateRequest, KBUpdateRequest, KBResponse,
    DocResponse, JobResponse,
)

router = APIRouter()


def _kb_resp(kb) -> KBResponse:
    return KBResponse(
        kb_id=kb.kb_id, name=kb.name, description=kb.description,
        config_name=kb.config_name, status=kb.status,
        doc_count=kb.doc_count, chunk_count=kb.chunk_count,
        owner_id=kb.owner_id, created_at=kb.created_at, updated_at=kb.updated_at,
    )


def _doc_resp(d) -> DocResponse:
    return DocResponse(
        doc_id=d.doc_id, kb_id=d.kb_id, filename=d.filename,
        file_type=d.file_type, file_size=d.file_size,
        upload_time=d.upload_time, parse_status=d.parse_status,
        parse_error=d.parse_error, chunk_count=d.chunk_count,
    )


def _job_resp(j) -> JobResponse:
    return JobResponse(
        job_id=j.job_id, kb_id=j.kb_id, job_type=j.job_type,
        status=j.status, progress=j.progress, stage_msg=j.stage_msg,
        started_at=j.started_at, finished_at=j.finished_at,
        error_msg=j.error_msg, stats_json=j.stats_json,
    )


# --- KB CRUD ---

@router.get("/", response_model=List[KBResponse])
def list_kbs(mgr=Depends(get_kb_manager), user=Depends(get_current_user)):
    return [_kb_resp(kb) for kb in mgr.list_kbs()]


@router.post("/", response_model=KBResponse, status_code=201)
def create_kb(body: KBCreateRequest, mgr=Depends(get_kb_manager),
              user=Depends(get_current_user)):
    kb_id = mgr.create_kb(
        name=body.name,
        description=body.description,
        config_name=body.config_name,
        owner_id=user.user_id,
    )
    return _kb_resp(mgr.get_kb(kb_id))


@router.get("/{kb_id}", response_model=KBResponse)
def get_kb(kb_id: str, mgr=Depends(get_kb_manager), user=Depends(get_current_user)):
    kb = mgr.get_kb(kb_id)
    if kb is None:
        raise HTTPException(404, "知识库不存在")
    return _kb_resp(kb)


@router.patch("/{kb_id}", response_model=KBResponse)
def update_kb(kb_id: str, body: KBUpdateRequest,
              mgr=Depends(get_kb_manager), user=Depends(get_current_user)):
    kb = mgr.get_kb(kb_id)
    if kb is None:
        raise HTTPException(404, "知识库不存在")
    updates = body.model_dump(exclude_none=True)
    if updates:
        mgr.update_kb(kb_id, **updates)
    return _kb_resp(mgr.get_kb(kb_id))


@router.delete("/{kb_id}", status_code=204)
def delete_kb(kb_id: str, confirm: bool = Query(False),
              mgr=Depends(get_kb_manager), user=Depends(get_current_user)):
    if not confirm:
        raise HTTPException(400, "请传 confirm=true 确认删除")
    kb = mgr.get_kb(kb_id)
    if kb is None:
        raise HTTPException(404, "知识库不存在")
    mgr.delete_kb(kb_id)


# --- Files ---

@router.post("/{kb_id}/files", response_model=DocResponse, status_code=201)
async def upload_file(kb_id: str, file: UploadFile = File(...),
                      mgr=Depends(get_kb_manager), user=Depends(get_current_user)):
    if mgr.get_kb(kb_id) is None:
        raise HTTPException(404, "知识库不存在")
    content = await file.read()
    doc_id = mgr.upload_file(kb_id, file.filename, content)
    doc = mgr.meta.get_document(doc_id)
    return _doc_resp(doc)


@router.get("/{kb_id}/files", response_model=List[DocResponse])
def list_files(kb_id: str, mgr=Depends(get_kb_manager), user=Depends(get_current_user)):
    if mgr.get_kb(kb_id) is None:
        raise HTTPException(404, "知识库不存在")
    return [_doc_resp(d) for d in mgr.list_documents(kb_id)]


@router.delete("/{kb_id}/files/{doc_id}", status_code=204)
def delete_file(kb_id: str, doc_id: str,
                mgr=Depends(get_kb_manager), user=Depends(get_current_user)):
    mgr.delete_document(doc_id)


@router.get("/{kb_id}/files/{doc_id}/download")
def download_file(kb_id: str, doc_id: str,
                  mgr=Depends(get_kb_manager), user=Depends(get_current_user)):
    """下载原始文件"""
    from fastapi.responses import FileResponse
    doc = mgr.meta.get_document(doc_id)
    if doc is None:
        raise HTTPException(404, "文档不存在")
    local_path = doc.storage_path
    if not local_path or not Path(local_path).exists():
        # 尝试从 storage_path 解析
        local_path = mgr.fs.get_local_path(doc.storage_path)
    if not Path(local_path).exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(local_path, filename=doc.filename, media_type="application/pdf")


@router.get("/{kb_id}/files/{doc_id}/parsed")
def get_parsed_content(kb_id: str, doc_id: str,
                       mgr=Depends(get_kb_manager), user=Depends(get_current_user)):
    """获取文档的解析结果（Markdown 内容）"""
    import json as _json
    doc = mgr.meta.get_document(doc_id)
    if doc is None:
        raise HTTPException(404, "文档不存在")

    # 从 parsed 目录查找对应的 JSON 文件
    parsed_dir = mgr.fs.get_dir_path(kb_id, "parsed")
    if not parsed_dir.exists():
        # 尝试全局 parsed 目录
        parsed_dir = ROOT / "data" / "parsed"

    # 通过 storage_path 的 sha1 或文件名匹配
    matched_file = None
    for f in parsed_dir.glob("*.json"):
        try:
            data = _json.loads(f.read_text(encoding="utf-8"))
            source = data.get("metainfo", {}).get("source", "")
            if source == doc.filename:
                matched_file = f
                break
        except Exception:
            continue

    if matched_file is None:
        raise HTTPException(404, "解析结果不存在，请先解析该文档")

    data = _json.loads(matched_file.read_text(encoding="utf-8"))
    pages = data.get("content", {}).get("pages", [])
    markdown = data.get("content", {}).get("markdown", "")
    total_pages = data.get("metainfo", {}).get("total_pages", 0)

    return {
        "filename": doc.filename,
        "total_pages": total_pages,
        "pages": pages,
        "markdown": markdown,
    }


# --- Jobs ---

@router.post("/{kb_id}/parse", response_model=JobResponse, status_code=202)
def start_parse(kb_id: str, mgr=Depends(get_kb_manager), user=Depends(get_current_user)):
    if mgr.get_kb(kb_id) is None:
        raise HTTPException(404, "知识库不存在")
    job_id = mgr.start_parse_job(kb_id)
    return _job_resp(mgr.get_job(job_id))


@router.post("/{kb_id}/index", response_model=JobResponse, status_code=202)
def start_index(kb_id: str, mgr=Depends(get_kb_manager), user=Depends(get_current_user)):
    if mgr.get_kb(kb_id) is None:
        raise HTTPException(404, "知识库不存在")
    job_id = mgr.start_index_job(kb_id)
    return _job_resp(mgr.get_job(job_id))


@router.post("/{kb_id}/process", response_model=JobResponse, status_code=202)
def start_full(kb_id: str, mgr=Depends(get_kb_manager), user=Depends(get_current_user)):
    """一键触发完整处理流程（解析 + 索引）"""
    if mgr.get_kb(kb_id) is None:
        raise HTTPException(404, "知识库不存在")
    job_id = mgr.start_full_job(kb_id)
    return _job_resp(mgr.get_job(job_id))


@router.get("/{kb_id}/jobs", response_model=List[JobResponse])
def list_jobs(kb_id: str, mgr=Depends(get_kb_manager), user=Depends(get_current_user)):
    return [_job_resp(j) for j in mgr.list_jobs(kb_id)]


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, mgr=Depends(get_kb_manager), user=Depends(get_current_user)):
    job = mgr.get_job(job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    return _job_resp(job)
