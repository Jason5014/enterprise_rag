from pydantic import BaseModel
from typing import Optional, List


class KBCreateRequest(BaseModel):
    name: str
    description: str = ""
    config_name: str = "base"
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    parent_chunk_size: Optional[int] = None
    split_method: str = "fixed"
    enable_parent_retrieval: Optional[bool] = None


class KBUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config_name: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    parent_chunk_size: Optional[int] = None
    split_method: Optional[str] = None
    enable_parent_retrieval: Optional[bool] = None


class KBResponse(BaseModel):
    kb_id: str
    name: str
    description: str
    config_name: str
    status: str
    doc_count: int
    chunk_count: int
    owner_id: Optional[str]
    created_at: str
    updated_at: str
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    parent_chunk_size: Optional[int] = None
    split_method: str = "fixed"
    enable_parent_retrieval: Optional[bool] = None


class DocResponse(BaseModel):
    doc_id: str
    kb_id: str
    filename: str
    file_type: str
    file_size: int
    upload_time: str
    parse_status: str
    parse_error: Optional[str]
    chunk_count: int


class JobResponse(BaseModel):
    job_id: str
    kb_id: str
    job_type: str
    status: str
    progress: float
    stage_msg: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    error_msg: Optional[str]
    stats_json: Optional[str]
