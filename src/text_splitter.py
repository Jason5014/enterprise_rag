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
    """文本分块器 - 支持父子Chunk和多种分片策略"""

    SUPPORTED_METHODS = ("fixed", "recursive", "sentence", "sliding")

    def __init__(self, config: Optional[RetrievalConfig] = None):
        self.config = config or RetrievalConfig()
        self.chunk_size = self.config.chunk_size
        self.chunk_overlap = self.config.chunk_overlap
        self.parent_chunk_size = self.config.parent_chunk_size
        self.enable_parent = self.config.enable_parent_retrieval
        self.split_method = getattr(self.config, 'split_method', 'fixed')
        if self.split_method not in self.SUPPORTED_METHODS:
            logger.warning("未知分片策略 '%s'，回退到 fixed", self.split_method)
            self.split_method = "fixed"
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
        segments = self._split_into_segments(text, self.parent_chunk_size, self.chunk_overlap)
        parent_chunks = []
        offset = 0
        for i, seg in enumerate(segments):
            # 计算在原文中的位置
            start = text.find(seg, offset) if offset < len(text) else offset
            if start < 0:
                start = offset
            parent_id = f"{doc_id}_parent_{i}" if doc_id else f"parent_{uuid.uuid4().hex[:8]}"
            parent_chunks.append(ParentChunk(
                text=seg,
                parent_id=parent_id,
                metadata={"doc_id": doc_id, "char_start": start, "char_end": start + len(seg), "parent_idx": i}
            ))
            offset = start + len(seg)
        return parent_chunks

    def _create_child_chunks(self, parent_chunks: List[ParentChunk]) -> List[Chunk]:
        """从父Chunk创建子Chunk"""
        child_chunks = []
        for parent in parent_chunks:
            segments = self._split_into_segments(parent.text, self.chunk_size, self.chunk_overlap)
            for j, seg in enumerate(segments):
                chunk_id = f"{parent.parent_id}_child_{j}"
                child_chunks.append(Chunk(
                    text=seg, chunk_id=chunk_id, parent_id=parent.parent_id,
                    metadata={**parent.metadata, "child_idx": j}
                ))
        return child_chunks

    def _create_child_chunks_from_parents(self, parent_chunks: List[ParentChunk]) -> List[Chunk]:
        """直接从父Chunk文本创建子Chunk（不维护父子关系）"""
        child_chunks = []
        for parent in parent_chunks:
            segments = self._split_into_segments(parent.text, self.chunk_size, self.chunk_overlap)
            for j, seg in enumerate(segments):
                chunk_id = f"{parent.parent_id}_c{j}"
                child_chunks.append(Chunk(
                    text=seg, chunk_id=chunk_id, parent_id=None,
                    metadata={**parent.metadata, "child_idx": j}
                ))
        return child_chunks

    # ------------------------------------------------------------------
    # 策略分发
    # ------------------------------------------------------------------

    def _split_into_segments(self, text: str, max_size: int, overlap: int) -> List[str]:
        """根据 split_method 将文本分成若干段"""
        if not text or not text.strip():
            return []
        if self.split_method == "recursive":
            return self._split_recursive(text, max_size, overlap)
        elif self.split_method == "sentence":
            return self._split_sentence(text, max_size, overlap)
        elif self.split_method == "sliding":
            return self._split_sliding(text, max_size, overlap)
        else:  # fixed
            return self._split_fixed(text, max_size, overlap)

    # ------------------------------------------------------------------
    # 策略 1: fixed — 固定大小 + 句子边界检测（原有逻辑）
    # ------------------------------------------------------------------

    def _split_fixed(self, text: str, max_size: int, overlap: int) -> List[str]:
        segments = []
        start = 0
        while start < len(text):
            end = min(start + max_size, len(text))
            chunk_text = text[start:end]
            if end < len(text):
                split_pos = self._find_best_split_position(chunk_text)
                if split_pos > 0:
                    chunk_text = chunk_text[:split_pos]
                    end = start + split_pos
            segments.append(chunk_text.strip())
            new_start = end - overlap
            if new_start <= start:
                new_start = end
            start = new_start
        return [s for s in segments if s]

    def _find_best_split_position(self, text: str) -> int:
        """在最后1/4区域查找分隔符"""
        search_start = len(text) * 3 // 4
        search_region = text[search_start:]
        for separator in ["\n\n", "\n", " "]:
            last_pos = search_region.rfind(separator)
            if last_pos >= 0:
                return search_start + last_pos
        return len(text) * 3 // 4

    # ------------------------------------------------------------------
    # 策略 2: recursive — 递归分割（先段落，再句子，再字符）
    # ------------------------------------------------------------------

    def _split_recursive(self, text: str, max_size: int, overlap: int) -> List[str]:
        separators = ["\n\n", "\n", "。", "！", "？", ". ", "! ", "? ", " ", ""]
        return self._recursive_split(text, max_size, overlap, separators, 0)

    def _recursive_split(self, text: str, max_size: int, overlap: int,
                         separators: List[str], depth: int) -> List[str]:
        if len(text) <= max_size:
            return [text.strip()] if text.strip() else []

        # 选择当前层级的分隔符
        if depth >= len(separators):
            # 所有分隔符都试过了，强制按大小截断
            return self._split_fixed(text, max_size, overlap)

        sep = separators[depth]
        if sep == "":
            parts = [text[i:i + max_size] for i in range(0, len(text), max_size)]
        else:
            parts = text.split(sep)

        # 合并小片段
        merged = []
        current = ""
        for part in parts:
            candidate = current + sep + part if current else part
            if len(candidate) <= max_size:
                current = candidate
            else:
                if current:
                    merged.append(current)
                current = part
        if current:
            merged.append(current)

        # 对仍然过大的片段递归处理
        result = []
        for chunk in merged:
            if len(chunk) > max_size:
                result.extend(self._recursive_split(chunk, max_size, overlap, separators, depth + 1))
            else:
                if chunk.strip():
                    result.append(chunk.strip())

        # 添加重叠
        if overlap > 0 and len(result) > 1:
            result = self._add_overlap_to_segments(result, overlap)

        return result

    # ------------------------------------------------------------------
    # 策略 3: sentence — 严格按句子边界分割
    # ------------------------------------------------------------------

    def _split_sentence(self, text: str, max_size: int, overlap: int) -> List[str]:
        # 按中英文句子结束符分割
        sentence_pattern = re.compile(r'(?<=[。！？.!?])\s*')
        sentences = sentence_pattern.split(text)
        sentences = [s.strip() for s in sentences if s.strip()]

        segments = []
        current = ""
        for sent in sentences:
            candidate = current + sent if current else sent
            if len(candidate) <= max_size:
                current = candidate
            else:
                if current:
                    segments.append(current)
                # 单句超长时按 fixed 处理
                if len(sent) > max_size:
                    segments.extend(self._split_fixed(sent, max_size, overlap))
                    current = ""
                else:
                    current = sent
        if current:
            segments.append(current)

        # 添加重叠
        if overlap > 0 and len(segments) > 1:
            segments = self._add_overlap_to_segments(segments, overlap)

        return [s for s in segments if s.strip()]

    # ------------------------------------------------------------------
    # 策略 4: sliding — 滑动窗口（固定步长，无边界检测）
    # ------------------------------------------------------------------

    def _split_sliding(self, text: str, max_size: int, overlap: int) -> List[str]:
        step = max_size - overlap
        if step <= 0:
            step = max_size
        segments = []
        start = 0
        while start < len(text):
            end = min(start + max_size, len(text))
            chunk = text[start:end].strip()
            if chunk:
                segments.append(chunk)
            if end >= len(text):
                break
            start += step
        return segments

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _add_overlap_to_segments(self, segments: List[str], overlap: int) -> List[str]:
        """为分段列表添加前后重叠"""
        if len(segments) <= 1:
            return segments
        result = [segments[0]]
        for i in range(1, len(segments)):
            prev_tail = segments[i - 1][-overlap:]
            result.append(prev_tail + segments[i])
        return result

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