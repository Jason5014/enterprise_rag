"""SQLiteMetadataStore — SQLite 元数据实现
TODO: 替换为 PostgresMetadataStore 时实现 MetadataStore 接口
"""
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import List, Optional

from .base import MetadataStore, UserRecord, KBRecord, DocRecord, JobRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    email         TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT DEFAULT 'user',
    is_active     INTEGER DEFAULT 1,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_bases (
    kb_id       TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    config_name TEXT DEFAULT 'base',
    status      TEXT DEFAULT 'empty',
    doc_count   INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    owner_id    TEXT REFERENCES users(user_id),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id       TEXT PRIMARY KEY,
    kb_id        TEXT NOT NULL REFERENCES knowledge_bases(kb_id) ON DELETE CASCADE,
    filename     TEXT NOT NULL,
    file_type    TEXT,
    file_size    INTEGER DEFAULT 0,
    storage_path TEXT DEFAULT '',
    upload_time  TEXT NOT NULL,
    parse_status TEXT DEFAULT 'pending',
    parse_error  TEXT,
    chunk_count  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS processing_jobs (
    job_id      TEXT PRIMARY KEY,
    kb_id       TEXT NOT NULL REFERENCES knowledge_bases(kb_id),
    job_type    TEXT,
    status      TEXT DEFAULT 'pending',
    progress    REAL DEFAULT 0.0,
    stage_msg   TEXT,
    started_at  TEXT,
    finished_at TEXT,
    error_msg   TEXT,
    stats_json  TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


class SQLiteMetadataStore(MetadataStore):

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # --- Users ---

    def create_user(self, username: str, email: Optional[str], password_hash: str,
                    role: str = "user") -> str:
        uid = _uid()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO users(user_id,username,email,password_hash,role,created_at)"
                " VALUES(?,?,?,?,?,?)",
                (uid, username, email, password_hash, role, _now()),
            )
        return uid

    def get_user_by_username(self, username: str) -> Optional[UserRecord]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username=?", (username,)
            ).fetchone()
        return self._row_to_user(row) if row else None

    def get_user_by_id(self, user_id: str) -> Optional[UserRecord]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id=?", (user_id,)
            ).fetchone()
        return self._row_to_user(row) if row else None

    @staticmethod
    def _row_to_user(row) -> UserRecord:
        return UserRecord(
            user_id=row["user_id"],
            username=row["username"],
            email=row["email"],
            password_hash=row["password_hash"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
        )

    # --- Knowledge Bases ---

    def create_kb(self, name: str, description: str, config_name: str,
                  owner_id: Optional[str] = None) -> str:
        kid = _uid()
        now = _now()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO knowledge_bases"
                "(kb_id,name,description,config_name,status,doc_count,chunk_count,owner_id,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (kid, name, description, config_name, "empty", 0, 0, owner_id, now, now),
            )
        return kid

    def get_kb(self, kb_id: str) -> Optional[KBRecord]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM knowledge_bases WHERE kb_id=?", (kb_id,)
            ).fetchone()
        return self._row_to_kb(row) if row else None

    def list_kbs(self, owner_id: Optional[str] = None) -> List[KBRecord]:
        with self._conn() as conn:
            if owner_id:
                rows = conn.execute(
                    "SELECT * FROM knowledge_bases WHERE owner_id=? ORDER BY created_at DESC",
                    (owner_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM knowledge_bases ORDER BY created_at DESC"
                ).fetchall()
        return [self._row_to_kb(r) for r in rows]

    def update_kb(self, kb_id: str, **fields) -> None:
        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [kb_id]
        with self._conn() as conn:
            conn.execute(
                f"UPDATE knowledge_bases SET {set_clause} WHERE kb_id=?", values
            )

    def delete_kb(self, kb_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM knowledge_bases WHERE kb_id=?", (kb_id,))

    @staticmethod
    def _row_to_kb(row) -> KBRecord:
        return KBRecord(
            kb_id=row["kb_id"],
            name=row["name"],
            description=row["description"] or "",
            config_name=row["config_name"],
            status=row["status"],
            doc_count=row["doc_count"],
            chunk_count=row["chunk_count"],
            owner_id=row["owner_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # --- Documents ---

    def create_document(self, kb_id: str, filename: str, file_type: str,
                        file_size: int, storage_path: str = "") -> str:
        did = _uid()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO documents"
                "(doc_id,kb_id,filename,file_type,file_size,storage_path,upload_time,parse_status)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (did, kb_id, filename, file_type, file_size, storage_path, _now(), "pending"),
            )
            conn.execute(
                "UPDATE knowledge_bases SET doc_count=doc_count+1, updated_at=? WHERE kb_id=?",
                (_now(), kb_id),
            )
        return did

    def get_document(self, doc_id: str) -> Optional[DocRecord]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE doc_id=?", (doc_id,)
            ).fetchone()
        return self._row_to_doc(row) if row else None

    def update_document(self, doc_id: str, **fields) -> None:
        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [doc_id]
        with self._conn() as conn:
            conn.execute(
                f"UPDATE documents SET {set_clause} WHERE doc_id=?", values
            )

    def list_documents(self, kb_id: str) -> List[DocRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE kb_id=? ORDER BY upload_time DESC",
                (kb_id,),
            ).fetchall()
        return [self._row_to_doc(r) for r in rows]

    def delete_document(self, doc_id: str) -> None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT kb_id FROM documents WHERE doc_id=?", (doc_id,)
            ).fetchone()
            if row:
                conn.execute("DELETE FROM documents WHERE doc_id=?", (doc_id,))
                conn.execute(
                    "UPDATE knowledge_bases SET doc_count=MAX(0,doc_count-1), updated_at=?"
                    " WHERE kb_id=?",
                    (_now(), row["kb_id"]),
                )

    @staticmethod
    def _row_to_doc(row) -> DocRecord:
        return DocRecord(
            doc_id=row["doc_id"],
            kb_id=row["kb_id"],
            filename=row["filename"],
            file_type=row["file_type"] or "",
            file_size=row["file_size"] or 0,
            storage_path=row["storage_path"] or "",
            upload_time=row["upload_time"],
            parse_status=row["parse_status"],
            parse_error=row["parse_error"],
            chunk_count=row["chunk_count"] or 0,
        )

    # --- Jobs ---

    def create_job(self, kb_id: str, job_type: str) -> str:
        jid = _uid()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO processing_jobs(job_id,kb_id,job_type,status)"
                " VALUES(?,?,?,?)",
                (jid, kb_id, job_type, "pending"),
            )
        return jid

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM processing_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        return self._row_to_job(row) if row else None

    def update_job(self, job_id: str, **fields) -> None:
        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [job_id]
        with self._conn() as conn:
            conn.execute(
                f"UPDATE processing_jobs SET {set_clause} WHERE job_id=?", values
            )

    def list_jobs(self, kb_id: str, limit: int = 10) -> List[JobRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM processing_jobs WHERE kb_id=?"
                " ORDER BY COALESCE(started_at, '') DESC LIMIT ?",
                (kb_id, limit),
            ).fetchall()
        return [self._row_to_job(r) for r in rows]

    @staticmethod
    def _row_to_job(row) -> JobRecord:
        return JobRecord(
            job_id=row["job_id"],
            kb_id=row["kb_id"],
            job_type=row["job_type"],
            status=row["status"],
            progress=row["progress"] or 0.0,
            stage_msg=row["stage_msg"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            error_msg=row["error_msg"],
            stats_json=row["stats_json"],
        )
