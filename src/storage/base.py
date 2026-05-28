"""存储抽象层接口 — 业务逻辑不依赖具体实现，将来替换 MinIO/PostgreSQL 时只换实现类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class FileInfo:
    filename: str
    storage_path: str   # 抽象路径（LocalFS: 绝对路径；MinIO: bucket/key）
    file_size: int
    file_type: str      # pdf / json / txt ...


@dataclass
class UserRecord:
    user_id: str
    username: str
    password_hash: str
    role: str           # admin / user
    is_active: bool
    created_at: str
    email: Optional[str] = None


@dataclass
class KBRecord:
    kb_id: str
    name: str
    description: str
    config_name: str
    status: str         # empty / processing / ready / error
    doc_count: int
    chunk_count: int
    created_at: str
    updated_at: str
    owner_id: Optional[str] = None
    index_dir: Optional[str] = None  # 覆盖默认索引路径，内置/迁移 KB 使用


@dataclass
class DocRecord:
    doc_id: str
    kb_id: str
    filename: str
    file_type: str
    file_size: int
    upload_time: str
    parse_status: str   # pending / processing / done / failed
    chunk_count: int = 0
    storage_path: str = ""
    parse_error: Optional[str] = None


@dataclass
class JobRecord:
    job_id: str
    kb_id: str
    job_type: str       # parse / index / full
    status: str         # pending / running / done / failed
    progress: float = 0.0
    stage_msg: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error_msg: Optional[str] = None
    stats_json: Optional[str] = None


# ---------------------------------------------------------------------------
# 文件存储接口
# ---------------------------------------------------------------------------

class FileStorage(ABC):
    """文件存储接口 — LocalFS 现在 / MinIO·S3 将来

    TODO: 替换为 MinIO/S3Storage 时实现此接口
    """

    @abstractmethod
    def save(self, kb_id: str, category: str, filename: str, content: bytes) -> str:
        """保存文件，返回抽象存储路径"""

    @abstractmethod
    def load(self, storage_path: str) -> bytes:
        """按抽象路径读取文件内容"""

    @abstractmethod
    def delete(self, storage_path: str) -> bool:
        """删除文件，返回是否成功"""

    @abstractmethod
    def list_files(self, kb_id: str, category: str) -> List[FileInfo]:
        """列出某 KB 某分类下的所有文件"""

    @abstractmethod
    def get_local_path(self, storage_path: str) -> Path:
        """返回可供本地工具（FAISS/MinerU）直接使用的文件系统路径。
        MinIO 实现时先下载到临时目录再返回路径。"""

    @abstractmethod
    def exists(self, storage_path: str) -> bool:
        """判断文件是否存在"""

    @abstractmethod
    def get_dir_path(self, kb_id: str, category: str) -> Path:
        """返回某 KB 某分类的目录路径（本地 FS 直接返回；MinIO 返回临时缓存目录）"""

    @abstractmethod
    def delete_kb(self, kb_id: str) -> None:
        """删除整个知识库的文件目录"""


# ---------------------------------------------------------------------------
# 元数据存储接口
# ---------------------------------------------------------------------------

class MetadataStore(ABC):
    """元数据存储接口 — SQLite 现在 / PostgreSQL 将来

    TODO: 替换为 PostgresMetadataStore 时实现此接口
    """

    # --- Users ---

    @abstractmethod
    def create_user(self, username: str, email: Optional[str], password_hash: str,
                    role: str = "user") -> str:
        """创建用户，返回 user_id"""

    @abstractmethod
    def get_user_by_username(self, username: str) -> Optional[UserRecord]:
        ...

    @abstractmethod
    def get_user_by_id(self, user_id: str) -> Optional[UserRecord]:
        ...

    # --- Knowledge Bases ---

    @abstractmethod
    def create_kb(self, name: str, description: str, config_name: str,
                  owner_id: Optional[str] = None) -> str:
        """创建知识库，返回 kb_id"""

    @abstractmethod
    def get_kb(self, kb_id: str) -> Optional[KBRecord]:
        ...

    @abstractmethod
    def list_kbs(self, owner_id: Optional[str] = None) -> List[KBRecord]:
        ...

    @abstractmethod
    def update_kb(self, kb_id: str, **fields) -> None:
        ...

    @abstractmethod
    def delete_kb(self, kb_id: str) -> None:
        ...

    # --- Documents ---

    @abstractmethod
    def create_document(self, kb_id: str, filename: str, file_type: str,
                        file_size: int, storage_path: str = "") -> str:
        """创建文档记录，返回 doc_id"""

    @abstractmethod
    def get_document(self, doc_id: str) -> Optional[DocRecord]:
        ...

    @abstractmethod
    def update_document(self, doc_id: str, **fields) -> None:
        ...

    @abstractmethod
    def list_documents(self, kb_id: str) -> List[DocRecord]:
        ...

    @abstractmethod
    def delete_document(self, doc_id: str) -> None:
        ...

    # --- Jobs ---

    @abstractmethod
    def create_job(self, kb_id: str, job_type: str) -> str:
        """创建处理任务，返回 job_id"""

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[JobRecord]:
        ...

    @abstractmethod
    def update_job(self, job_id: str, **fields) -> None:
        ...

    @abstractmethod
    def list_jobs(self, kb_id: str, limit: int = 10) -> List[JobRecord]:
        ...
