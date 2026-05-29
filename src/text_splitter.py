"""文本分块模块 - 支持父子Chunk关联"""
import re
import uuid
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

from config.retrieval_config import RetrievalConfig


class Chunk:
    """分块对象"""

    def __init__(self, text: str, chunk_id: str, parent_id: Optional[str] = None,
                 metadata: Optional[Dict[str, Any]] = None):
        self.chunk_id = chunk_id
        self.parent_id = parent_id
        self.text = text
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "parent_id": self.parent_id,
            "text": self.text,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Chunk":
        return cls(
            text=d["text"],
            chunk_id=d["chunk_id"],
            parent_id=d.get("parent_id"),
            metadata=d.get("metadata", {})
        )


class ParentChunk(Chunk):
    """父Chunk"""
    # 注意：parent_id 在 ParentChunk 中表示父Chunk的唯一标识（即chunk_id）

    def __init__(self, text: str, parent_id: str,
                 metadata: Optional[Dict[str, Any]] = None):
        super().__init__(text, chunk_id=parent_id, parent_id=parent_id, metadata=metadata)
        self.chunk_id = parent_id
        self.parent_id = parent_id  # 父Chunk的parent_id就是它自己的chunk_id


class TextSplitter:
    """文本分块器 - 支持父子Chunk"""

    def __init__(self, config: Optional[RetrievalConfig] = None):
        self.config = config or RetrievalConfig()
        self.chunk_size = self.config.chunk_size
        self.chunk_overlap = self.config.chunk_overlap
        self.parent_chunk_size = self.config.parent_chunk_size
        self.enable_parent = self.config.enable_parent_retrieval
        self.separators = ["\n\n", "\n", " ", ""]

    def split_text(self, text: str, doc_id: str = "") -> Tuple[List[Chunk], List[ParentChunk]]:
        """
        分块文本，返回子Chunk和父Chunk

        Returns:
            (child_chunks, parent_chunks)
        """
        if not text or not text.strip():
            return [], []

        # 先按父Chunk大小分割成父Chunk
        parent_chunks = self._create_parent_chunks(text, doc_id)

        if not self.enable_parent:
            # 不启用父子检索，直接返回子Chunk
            child_chunks = self._create_child_chunks_from_parents(parent_chunks)
            return child_chunks, []

        # 创建子Chunk
        child_chunks = self._create_child_chunks(parent_chunks)

        return child_chunks, parent_chunks

    def _create_parent_chunks(self, text: str, doc_id: str) -> List[ParentChunk]:
        """创建父Chunk"""
        parent_chunks = []
        start = 0
        parent_idx = 0

        while start < len(text):
            end = min(start + self.parent_chunk_size, len(text))
            chunk_text = text[start:end]

            # 尝试在合适的位置分割（不切断句子）
            if end < len(text):
                split_pos = self._find_best_split_position(chunk_text)
                if split_pos > 0:
                    chunk_text = chunk_text[:split_pos]
                    end = start + split_pos

            # 防止无限循环：当剩余文本不足时，直接取到最后
            remaining = len(text) - end
            if remaining <= 0:
                # 已经处理完或剩余太少，直接取剩余文本并结束
                if start < len(text):
                    chunk_text = text[start:].strip()
                    if chunk_text:
                        parent_id = f"{doc_id}_parent_{parent_idx}" if doc_id else f"parent_{uuid.uuid4().hex[:8]}"
                        parent = ParentChunk(
                            text=chunk_text,
                            parent_id=parent_id,
                            metadata={
                                "doc_id": doc_id,
                                "char_start": start,
                                "char_end": len(text),
                                "parent_idx": parent_idx
                            }
                        )
                        parent_chunks.append(parent)
                break

            parent_id = f"{doc_id}_parent_{parent_idx}" if doc_id else f"parent_{uuid.uuid4().hex[:8]}"
            parent = ParentChunk(
                text=chunk_text.strip(),
                parent_id=parent_id,
                metadata={
                    "doc_id": doc_id,
                    "char_start": start,
                    "char_end": end,
                    "parent_idx": parent_idx
                }
            )
            parent_chunks.append(parent)

            parent_idx += 1
            start = end - self.chunk_overlap
            if start < 0:
                start = end  # 无重叠时直接跳到当前结束位置
            if start >= len(text):
                break
            # 防止小重叠导致的死循环：剩余文本小于overlap*2时直接处理完
            if len(text) - start < self.chunk_overlap * 2:
                start = len(text)  # 剩余太少，直接结束

        return parent_chunks

    def _create_child_chunks(self, parent_chunks: List[ParentChunk]) -> List[Chunk]:
        """从父Chunk创建子Chunk"""
        child_chunks = []

        for parent in parent_chunks:
            start = 0
            child_idx = 0
            parent_text = parent.text

            while start < len(parent_text):
                end = min(start + self.chunk_size, len(parent_text))
                child_text = parent_text[start:end]

                # 尝试在合适的位置分割
                if end < len(parent_text):
                    split_pos = self._find_best_split_position(child_text)
                    if split_pos > 0:
                        child_text = child_text[:split_pos]
                        end = start + split_pos

                chunk_id = f"{parent.parent_id}_child_{child_idx}"
                child = Chunk(
                    text=child_text.strip(),
                    chunk_id=chunk_id,
                    parent_id=parent.parent_id,
                    metadata={
                        **parent.metadata,
                        "child_idx": child_idx
                    }
                )
                child_chunks.append(child)

                child_idx += 1
                start = end - self.chunk_overlap
                if start < 0:
                    start = end
                if start >= len(parent_text):
                    break
                # 防止小重叠导致的死循环
                if len(parent_text) - start < self.chunk_overlap * 2:
                    start = len(parent_text)

        return child_chunks

    def _create_child_chunks_from_parents(self, parent_chunks: List[ParentChunk]) -> List[Chunk]:
        """直接从父Chunk文本创建子Chunk（不维护父子关系）"""
        child_chunks = []

        for parent in parent_chunks:
            start = 0
            child_idx = 0
            parent_text = parent.text

            while start < len(parent_text):
                end = min(start + self.chunk_size, len(parent_text))
                child_text = parent_text[start:end]

                if end < len(parent_text):
                    split_pos = self._find_best_split_position(child_text)
                    if split_pos > 0:
                        child_text = child_text[:split_pos]
                        end = start + split_pos

                chunk_id = f"{parent.parent_id}_c{child_idx}"
                child = Chunk(
                    text=child_text.strip(),
                    chunk_id=chunk_id,
                    parent_id=None,
                    metadata={
                        **parent.metadata,
                        "child_idx": child_idx
                    }
                )
                child_chunks.append(child)

                child_idx += 1
                start = end - self.chunk_overlap
                if start < 0:
                    start = end
                if start >= len(parent_text):
                    break

        return child_chunks

    def _find_best_split_position(self, text: str) -> int:
        """找到最佳分割位置（句子边界）- 在最后1/4区域查找分隔符"""
        search_start = len(text) * 3 // 4

        # 只在最后1/4区域搜索，避免大文本下rfind扫描整个字符串
        search_region = text[search_start:]

        for separator in ["\n\n", "\n", " "]:
            last_pos = search_region.rfind(separator)
            if last_pos >= 0:
                return search_start + last_pos

        # 如果找不到合适的分隔符，在3/4位置强制截断
        return len(text) * 3 // 4

    def split_documents(self, documents: List[Dict[str, Any]], doc_id_field: str = "doc_id") -> Dict[str, Any]:
        """
        批量分块文档

        Args:
            documents: [{"text": "...", "doc_id": "...", "metadata": {...}}, ...]
            doc_id_field: 文档中ID字段名

        Returns:
            {"chunks": [...], "parent_chunks": [...], "metadata": {...}}
        """
        all_child_chunks = []
        all_parent_chunks = []
        stats = {"total_docs": 0, "total_child_chunks": 0, "total_parent_chunks": 0}

        for doc in documents:
            text = doc.get("text", "")
            doc_id = doc.get(doc_id_field, "")
            extra_metadata = doc.get("metadata", {})

            if not text:
                continue

            # 分割
            child_chunks, parent_chunks = self.split_text(text, doc_id)

            # 添加额外元数据
            for chunk in child_chunks:
                chunk.metadata.update(extra_metadata)

            for parent in parent_chunks:
                parent.metadata.update(extra_metadata)

            all_child_chunks.extend(child_chunks)
            all_parent_chunks.extend(parent_chunks)
            stats["total_docs"] += 1

        stats["total_child_chunks"] = len(all_child_chunks)
        stats["total_parent_chunks"] = len(all_parent_chunks)

        return {
            "chunks": [c.to_dict() for c in all_child_chunks],
            "parent_chunks": [p.to_dict() for p in all_parent_chunks],
            "metadata": stats
        }


    def split_directory(self, directory: str) -> List[Dict[str, Any]]:
        """
        读取目录下的解析结果文件并分块，保留页码信息。

        支持两种格式：
        - JSON 文件（MinerU 解析输出）：从 content.pages 按页分块
        - Markdown 文件：整文件作为一个文档分块

        Args:
            directory: 包含解析结果的目录路径

        Returns:
            扁平化的 chunk 字典列表（包含 text, chunk_id, parent_id, metadata）
        """
        dir_path = Path(directory)
        documents = []

        # 优先读取 JSON 文件（MinerU 解析输出）
        for json_file in sorted(dir_path.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("读取 JSON 失败 %s: %s", json_file.name, e)
                continue

            source = data.get("metainfo", {}).get("source", json_file.stem)
            pages = data.get("content", {}).get("pages", [])

            if pages:
                # 按页创建文档，保留页码
                for page_data in pages:
                    page_text = page_data.get("text", "").strip()
                    if not page_text:
                        continue
                    page_num = page_data.get("page", 0)
                    doc_id = f"{json_file.stem}_p{page_num}"
                    documents.append({
                        "text": page_text,
                        "doc_id": doc_id,
                        "metadata": {
                            "source_file": source,
                            "page": page_num,
                        }
                    })
            else:
                # 无 pages 数组，尝试从 markdown 字段读取
                md = data.get("content", {}).get("markdown", "")
                if md.strip():
                    documents.append({
                        "text": md,
                        "doc_id": json_file.stem,
                        "metadata": {"source_file": source}
                    })

        # 兜底：也读取 .md 文件
        for md_file in sorted(dir_path.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            if not text.strip():
                continue
            documents.append({
                "text": text,
                "doc_id": md_file.stem,
                "metadata": {"source_file": md_file.name}
            })

        if not documents:
            logger.warning("目录 %s 下未找到可分块的文件", directory)
            return []

        result = self.split_documents(documents)
        return result["chunks"]


def text_splitter_cli():
    """CLI入口"""
    import sys
    import json

    if len(sys.argv) < 2:
        print("用法: python text_splitter.py <input.json> [output.json]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "data/chunked/chunks.json"

    # 读取文档
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    documents = data if isinstance(data, list) else data.get("documents", [])

    # 分块
    splitter = TextSplitter()
    result = splitter.split_documents(documents)

    # 保存结果
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info("分块完成: %s", result['metadata'])


if __name__ == "__main__":
    text_splitter_cli()