"""LocalFileStorage — 本地文件系统实现
TODO: 替换为 MinIOStorage / S3Storage 时实现 FileStorage 接口
"""
import os
import shutil
from pathlib import Path
from typing import List

from .base import FileStorage, FileInfo


class LocalFileStorage(FileStorage):
    """将文件存储在本地文件系统的 {base_dir}/kb/{kb_id}/{category}/ 目录下"""

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)

    def _dir(self, kb_id: str, category: str) -> Path:
        d = self.base_dir / "kb" / kb_id / category
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _abs(self, storage_path: str) -> Path:
        """抽象路径即绝对路径"""
        return Path(storage_path)

    def save(self, kb_id: str, category: str, filename: str, content: bytes) -> str:
        dest = self._dir(kb_id, category) / filename
        dest.write_bytes(content)
        return str(dest)

    def load(self, storage_path: str) -> bytes:
        return self._abs(storage_path).read_bytes()

    def delete(self, storage_path: str) -> bool:
        p = self._abs(storage_path)
        if p.exists():
            p.unlink()
            return True
        return False

    def list_files(self, kb_id: str, category: str) -> List[FileInfo]:
        d = self._dir(kb_id, category)
        result = []
        for p in sorted(d.iterdir()):
            if p.is_file():
                result.append(FileInfo(
                    filename=p.name,
                    storage_path=str(p),
                    file_size=p.stat().st_size,
                    file_type=p.suffix.lstrip("."),
                ))
        return result

    def get_local_path(self, storage_path: str) -> Path:
        return self._abs(storage_path)

    def exists(self, storage_path: str) -> bool:
        return self._abs(storage_path).exists()

    def get_dir_path(self, kb_id: str, category: str) -> Path:
        return self._dir(kb_id, category)

    def delete_kb(self, kb_id: str) -> None:
        kb_dir = self.base_dir / "kb" / kb_id
        if kb_dir.exists():
            shutil.rmtree(kb_dir)
