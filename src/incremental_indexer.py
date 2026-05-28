"""增量索引模块 - 监控文件变化自动更新索引"""
import os
import json
import hashlib
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
import threading

logger = logging.getLogger(__name__)

from config.indexer_config import IndexerConfig


WATCHDOG_AVAILABLE = False
FileSystemEventHandler = None
FileSystemEvent = None

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler as Handler, FileSystemEvent as Event
    WATCHDOG_AVAILABLE = True
    FileSystemEventHandler = Handler
    FileSystemEvent = Event
except ImportError:
    pass


class FileChangeHandler:
    """文件系统变化处理器（ watchdog 不可用时提供基础实现）"""

    def __init__(self, callback: Callable[[str, str], None], extensions: List[str] = None):
        self.callback = callback
        self.extensions = extensions or ['.pdf', '.PDF']

    def on_created(self, event):
        if not event.is_directory and self._is_watched_file(event.src_path):
            self.callback("created", event.src_path)

    def on_modified(self, event):
        if not event.is_directory and self._is_watched_file(event.src_path):
            self.callback("modified", event.src_path)

    def on_deleted(self, event):
        if not event.is_directory and self._is_watched_file(event.src_path):
            self.callback("deleted", event.src_path)

    def _is_watched_file(self, file_path: str) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in self.extensions


class IncrementalIndexer:
    """增量索引器"""

    def __init__(self, config: Optional[IndexerConfig] = None):
        self.config = config or IndexerConfig()
        self.watch_dir = Path(self.config.pdf_watch_dir)
        self.check_interval = self.config.check_interval
        self.auto_reindex = self.config.auto_reindex
        self.reindex_threshold = self.config.reindex_threshold

        self._observer = None
        self._file_hashes: Dict[str, str] = {}
        self._pending_changes: List[Dict[str, Any]] = []
        self._callbacks: List[Callable] = []
        self._running = False
        self._lock = threading.Lock()

    def start_watching(self) -> None:
        """启动文件监控"""
        if not WATCHDOG_AVAILABLE:
            raise ImportError("watchdog未安装，请运行: pip install watchdog")

        if not self.watch_dir.exists():
            raise FileNotFoundError(f"监控目录不存在: {self.watch_dir}")

        self._running = True
        self._observer = Observer()
        handler = FileChangeHandler(self._on_file_change)
        self._observer.schedule(handler, str(self.watch_dir), recursive=False)
        self._observer.start()

        self._check_thread = threading.Thread(target=self._periodic_check, daemon=True)
        self._check_thread.start()

    def stop_watching(self) -> None:
        """停止文件监控"""
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join()

    def register_callback(self, callback: Callable[[str, Path], None]) -> None:
        """注册变化回调函数"""
        self._callbacks.append(callback)

    def _on_file_change(self, event_type: str, file_path: str) -> None:
        """处理文件变化"""
        with self._lock:
            change = {
                "event_type": event_type,
                "file_path": file_path,
                "timestamp": datetime.now().isoformat()
            }
            self._pending_changes.append(change)

            for callback in self._callbacks:
                try:
                    callback(event_type, Path(file_path))
                except Exception as e:
                    logger.error("回调执行失败: %s", e)

    def _periodic_check(self) -> None:
        """定期检查文件变化"""
        while self._running:
            time.sleep(self.check_interval)
            self._scan_for_changes()

    def _scan_for_changes(self) -> None:
        """扫描检测变化"""
        with self._lock:
            if not self.watch_dir.exists():
                return

            current_files = set()
            for f in self.watch_dir.glob("*.pdf"):
                current_files.add(str(f))
            for f in self.watch_dir.glob("*.PDF"):
                current_files.add(str(f))

            for stored_file in list(self._file_hashes.keys()):
                if stored_file not in current_files:
                    self._pending_changes.append({
                        "event_type": "deleted",
                        "file_path": stored_file,
                        "timestamp": datetime.now().isoformat()
                    })
                    del self._file_hashes[stored_file]

    def get_pending_changes(self) -> List[Dict[str, Any]]:
        """获取待处理的变化"""
        with self._lock:
            changes = self._pending_changes.copy()
            self._pending_changes.clear()
            return changes

    def compute_file_hash(self, file_path: Path) -> str:
        """计算文件哈希"""
        sha1 = hashlib.sha1()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha1.update(chunk)
        return sha1.hexdigest()[:16]

    def scan_directory(self) -> Dict[str, Any]:
        """扫描目录，返回文件信息"""
        if not self.watch_dir.exists():
            return {"files": [], "total": 0}

        files = []
        for f in sorted(self.watch_dir.glob("*.pdf")):
            files.append({
                "path": str(f),
                "name": f.name,
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                "hash": self.compute_file_hash(f)
            })
        for f in sorted(self.watch_dir.glob("*.PDF")):
            files.append({
                "path": str(f),
                "name": f.name,
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                "hash": self.compute_file_hash(f)
            })

        self._file_hashes = {f["path"]: f["hash"] for f in files}

        return {
            "files": files,
            "total": len(files),
            "directory": str(self.watch_dir)
        }

    def should_full_reindex(self) -> bool:
        """判断是否需要全量重建索引"""
        changes = self.get_pending_changes()
        if not changes:
            return False

        changed_files = set(c["file_path"] for c in changes)
        total_files = len(self._file_hashes)
        if total_files == 0:
            return False

        change_ratio = len(changed_files) / total_files
        return change_ratio >= self.reindex_threshold


def incremental_index_cli():
    """CLI入口"""
    import sys

    if len(sys.argv) < 2:
        print("用法: python incremental_indexer.py <command>")
        print("命令:")
        print("  scan    - 扫描目录")
        print("  watch   - 启动监控")
        print("  status  - 显示状态")
        sys.exit(1)

    command = sys.argv[1]
    indexer = IncrementalIndexer()

    if command == "scan":
        result = indexer.scan_directory()
        logger.info("目录: %s", result['directory'])
        logger.info("文件数: %s", result['total'])
        for f in result['files']:
            logger.info("  %s (%s bytes, hash=%s)", f['name'], f['size'], f['hash'])

    elif command == "watch":
        print("启动文件监控...")
        indexer.start_watching()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            indexer.stop_watching()
            print("\n监控已停止")

    elif command == "status":
        logger.info("增量索引状态:")
        logger.info("  监控目录: %s", indexer.watch_dir)
        logger.info("  检查间隔: %s秒", indexer.check_interval)


if __name__ == "__main__":
    incremental_index_cli()