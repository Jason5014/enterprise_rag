from pydantic import BaseModel
from typing import Optional, List


class KBCreateRequest(BaseModel):
    name: str
    description: str = ""
    config_name: str = "base"


class KBUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config_name: Optional[str] = None


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
