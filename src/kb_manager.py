"""KBManager — 知识库管理模块，协调 FileStorage + MetadataStore + RAGPipeline"""
import copy
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class KBManager:
    """管理知识库的创建、文件上传、索引构建和查询管道获取。

    所有存储访问通过 FileStorage / MetadataStore 抽象接口，
    切换 MinIO 或 PostgreSQL 时只需更换注入实例，此模块不变。
    """

    def __init__(self, file_storage, metadata_store):
        """
        Args:
            file_storage: FileStorage 实例（LocalFileStorage 或 MinIOStorage）
            metadata_store: MetadataStore 实例（SQLiteMetadataStore 或 PostgresMetadataStore）
        """
        self.fs = file_storage
        self.meta = metadata_store
        self._pipelines: dict = {}      # kb_id -> RAGPipeline（已加载的缓存）
        self._pipeline_lock = threading.Lock()

    # ------------------------------------------------------------------
    # 知识库 CRUD
    # ------------------------------------------------------------------

    def create_kb(self, name: str, description: str = "", config_name: str = "base",
                  owner_id: Optional[str] = None) -> str:
        """创建知识库，返回 kb_id"""
        kb_id = self.meta.create_kb(name, description, config_name, owner_id)
        # 预建目录，方便后续文件上传不出错
        self.fs.get_dir_path(kb_id, "raw")
        self.fs.get_dir_path(kb_id, "parsed")
        self.fs.get_dir_path(kb_id, "chunked")
        logger.info("创建知识库 kb_id=%s name=%s", kb_id, name)
        return kb_id

    def list_kbs(self, owner_id: Optional[str] = None):
        return self.meta.list_kbs(owner_id)

    def get_kb(self, kb_id: str):
        return self.meta.get_kb(kb_id)

    def update_kb(self, kb_id: str, **fields):
        self.meta.update_kb(kb_id, **fields)

    def delete_kb(self, kb_id: str) -> None:
        """删除知识库及其所有文件和索引"""
        self.fs.delete_kb(kb_id)
        self.meta.delete_kb(kb_id)
        with self._pipeline_lock:
            self._pipelines.pop(kb_id, None)
        logger.info("删除知识库 kb_id=%s", kb_id)

    # ------------------------------------------------------------------
    # 文件管理
    # ------------------------------------------------------------------

    def upload_file(self, kb_id: str, filename: str, content: bytes) -> str:
        """上传文件到知识库，返回 doc_id"""
        file_type = Path(filename).suffix.lstrip(".").lower()
        storage_path = self.fs.save(kb_id, "raw", filename, content)
        doc_id = self.meta.create_document(
            kb_id=kb_id,
            filename=filename,
            file_type=file_type,
            file_size=len(content),
            storage_path=storage_path,
        )
        logger.info("上传文件 kb_id=%s filename=%s doc_id=%s", kb_id, filename, doc_id)
        return doc_id

    def list_documents(self, kb_id: str):
        return self.meta.list_documents(kb_id)

    def delete_document(self, doc_id: str) -> None:
        doc = self.meta.get_document(doc_id)
        if doc and doc.storage_path:
            self.fs.delete(doc.storage_path)
        self.meta.delete_document(doc_id)

    # ------------------------------------------------------------------
    # 处理任务：解析 + 索引
    # ------------------------------------------------------------------

    def start_parse_job(self, kb_id: str) -> str:
        """异步启动 PDF 解析任务，返回 job_id"""
        job_id = self.meta.create_job(kb_id, "parse")
        thread = threading.Thread(
            target=self._run_parse, args=(kb_id, job_id), daemon=True
        )
        thread.start()
        return job_id

    def start_index_job(self, kb_id: str) -> str:
        """异步启动索引构建任务，返回 job_id"""
        job_id = self.meta.create_job(kb_id, "index")
        thread = threading.Thread(
            target=self._run_index, args=(kb_id, job_id), daemon=True
        )
        thread.start()
        return job_id

    def start_full_job(self, kb_id: str) -> str:
        """异步启动完整流程（解析 + 索引），返回 job_id"""
        job_id = self.meta.create_job(kb_id, "full")
        thread = threading.Thread(
            target=self._run_full, args=(kb_id, job_id), daemon=True
        )
        thread.start()
        return job_id

    def get_job(self, job_id: str):
        return self.meta.get_job(job_id)

    def list_jobs(self, kb_id: str, limit: int = 10):
        return self.meta.list_jobs(kb_id, limit)

    # ------------------------------------------------------------------
    # 内部：后台任务执行
    # ------------------------------------------------------------------

    def _mark_job(self, job_id: str, status: str, **extra):
        now = datetime.now(timezone.utc).isoformat()
        fields = {"status": status, **extra}
        if status == "running" and "started_at" not in fields:
            fields["started_at"] = now
        if status in ("done", "failed"):
            fields["finished_at"] = now
        self.meta.update_job(job_id, **fields)

    def _run_parse(self, kb_id: str, job_id: str):
        self._mark_job(job_id, "running", stage_msg="开始解析")
        try:
            docs = self.meta.list_documents(kb_id)
            pdf_docs = [d for d in docs if d.file_type in ("pdf", "PDF")]
            parsed_dir = self.fs.get_dir_path(kb_id, "parsed")

            from src.pdf_mineru import MinerUAPI
            from config.pdf_config import PDFConfig
            api = MinerUAPI()
            total = len(pdf_docs)

            for i, doc in enumerate(pdf_docs):
                self._mark_job(job_id, "running",
                               stage_msg=f"解析 {doc.filename} ({i+1}/{total})",
                               progress=round(i / max(total, 1), 2))
                self.meta.update_document(doc.doc_id, parse_status="processing")
                try:
                    local_path = self.fs.get_local_path(doc.storage_path)
                    api.parse_file(str(local_path), str(parsed_dir))
                    self.meta.update_document(doc.doc_id, parse_status="done")
                except Exception as e:
                    logger.error("解析失败 doc_id=%s: %s", doc.doc_id, e)
                    self.meta.update_document(doc.doc_id,
                                              parse_status="failed",
                                              parse_error=str(e))

            self._mark_job(job_id, "done",
                           progress=1.0,
                           stage_msg="解析完成",
                           stats_json=json.dumps({"parsed_count": total}))
            self.meta.update_kb(kb_id, status="parsed")
        except Exception as e:
            logger.exception("解析任务异常 job_id=%s", job_id)
            self._mark_job(job_id, "failed", error_msg=str(e))
            self.meta.update_kb(kb_id, status="error")

    def _run_index(self, kb_id: str, job_id: str):
        self._mark_job(job_id, "running", stage_msg="开始构建索引")
        try:
            kb = self.meta.get_kb(kb_id)
            parsed_dir = self.fs.get_dir_path(kb_id, "parsed")
            chunked_dir = self.fs.get_dir_path(kb_id, "chunked")

            from config.presets import get_preset
            from src.text_splitter import TextSplitter
            from src.vector_store import VectorStore
            from src.bm25_index import BM25Index

            config = get_preset(kb.config_name)
            rc = config.retrieval
            ec = config.embedding

            self._mark_job(job_id, "running", stage_msg="加载解析结果", progress=0.1)
            splitter = TextSplitter(rc)
            chunks = splitter.split_directory(str(parsed_dir))

            self._mark_job(job_id, "running", stage_msg="构建向量索引", progress=0.4)
            vs = VectorStore(ec)
            vs.build_index(chunks)
            vs.save(str(chunked_dir))

            self._mark_job(job_id, "running", stage_msg="构建BM25索引", progress=0.8)
            bm25 = BM25Index()
            bm25.build(chunks)
            bm25.save(str(chunked_dir))

            chunk_count = len(chunks)
            self.meta.update_kb(kb_id, status="ready", chunk_count=chunk_count)
            self._mark_job(job_id, "done", progress=1.0,
                           stage_msg="索引构建完成",
                           stats_json=json.dumps({"chunk_count": chunk_count}))

            # 使缓存失效，下次查询重新加载新索引
            with self._pipeline_lock:
                self._pipelines.pop(kb_id, None)
        except Exception as e:
            logger.exception("索引任务异常 job_id=%s", job_id)
            self._mark_job(job_id, "failed", error_msg=str(e))
            self.meta.update_kb(kb_id, status="error")

    def _run_full(self, kb_id: str, job_id: str):
        """完整流程：先解析再索引，共用同一个 job"""
        self._mark_job(job_id, "running", stage_msg="开始完整处理", job_type="full")
        try:
            # 解析阶段
            docs = self.meta.list_documents(kb_id)
            pdf_docs = [d for d in docs if d.file_type in ("pdf", "PDF")]
            parsed_dir = self.fs.get_dir_path(kb_id, "parsed")

            if pdf_docs:
                from src.pdf_mineru import MinerUAPI
                api = MinerUAPI()
                total = len(pdf_docs)
                for i, doc in enumerate(pdf_docs):
                    self._mark_job(job_id, "running",
                                   stage_msg=f"[1/2] 解析 {doc.filename} ({i+1}/{total})",
                                   progress=round(0.4 * i / max(total, 1), 2))
                    self.meta.update_document(doc.doc_id, parse_status="processing")
                    try:
                        local_path = self.fs.get_local_path(doc.storage_path)
                        api.parse_file(str(local_path), str(parsed_dir))
                        self.meta.update_document(doc.doc_id, parse_status="done")
                    except Exception as e:
                        self.meta.update_document(doc.doc_id,
                                                  parse_status="failed",
                                                  parse_error=str(e))

            # 索引阶段
            kb = self.meta.get_kb(kb_id)
            chunked_dir = self.fs.get_dir_path(kb_id, "chunked")

            from config.presets import get_preset
            from src.text_splitter import TextSplitter
            from src.vector_store import VectorStore
            from src.bm25_index import BM25Index

            config = get_preset(kb.config_name)
            rc = config.retrieval
            ec = config.embedding

            self._mark_job(job_id, "running", stage_msg="[2/2] 构建向量索引", progress=0.5)
            splitter = TextSplitter(rc)
            chunks = splitter.split_directory(str(parsed_dir))

            vs = VectorStore(ec)
            vs.build_index(chunks)
            vs.save(str(chunked_dir))

            self._mark_job(job_id, "running", stage_msg="[2/2] 构建BM25索引", progress=0.85)
            bm25 = BM25Index()
            bm25.build(chunks)
            bm25.save(str(chunked_dir))

            chunk_count = len(chunks)
            self.meta.update_kb(kb_id, status="ready", chunk_count=chunk_count)
            self._mark_job(job_id, "done", progress=1.0,
                           stage_msg="处理完成",
                           stats_json=json.dumps({"chunk_count": chunk_count}))

            with self._pipeline_lock:
                self._pipelines.pop(kb_id, None)
        except Exception as e:
            logger.exception("完整任务异常 job_id=%s", job_id)
            self._mark_job(job_id, "failed", error_msg=str(e))
            self.meta.update_kb(kb_id, status="error")

    # ------------------------------------------------------------------
    # 查询管道
    # ------------------------------------------------------------------

    def get_pipeline(self, kb_id: str):
        """获取（并缓存）某知识库的 RAGPipeline。首次调用加载索引。"""
        with self._pipeline_lock:
            if kb_id in self._pipelines:
                return self._pipelines[kb_id]

        kb = self.meta.get_kb(kb_id)
        if kb is None:
            raise ValueError(f"知识库不存在: {kb_id}")

        from config.presets import get_preset
        from config.retrieval_config import RetrievalConfig
        from src.pipeline import RAGPipeline

        config = get_preset(kb.config_name)
        # 深拷贝避免修改共享预设
        rc = copy.deepcopy(config.retrieval) if config.retrieval else RetrievalConfig()
        rc.index_dir = str(self.fs.get_dir_path(kb_id, "chunked"))
        config.retrieval = rc

        pipeline = RAGPipeline(config)
        with self._pipeline_lock:
            self._pipelines[kb_id] = pipeline

        logger.info("加载知识库管道 kb_id=%s index_dir=%s", kb_id, rc.index_dir)
        return pipeline
