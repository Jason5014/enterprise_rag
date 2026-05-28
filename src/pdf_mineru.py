"""PDF解析模块 - 使用MinerU在线API"""
import os
import json
import time
import hashlib
import logging
import requests
from pathlib import Path
from typing import Dict, Any, Optional, List
from tqdm import tqdm

logger = logging.getLogger(__name__)

from config.pdf_config import PDFConfig


class MinerUAPI:
    """MinerU API客户端"""

    PRECISION_API_URL = "https://mineru.net/api/v4/extract/task"
    AGENT_API_URL = "https://mineru.net/api/v1/agent/parse/url"
    RESULT_URL = "https://mineru.net/api/v1/agent/parse/{task_id}"

    def __init__(self, api_key: Optional[str] = None, use_agent_api: bool = True):
        """
        初始化MinerU API客户端

        Args:
            api_key: API密钥（Precision API需要）
            use_agent_api: True使用Agent API（无需登录），False使用Precision API
        """
        self.api_key = api_key or os.getenv("MINERU_API_KEY", "")
        self.use_agent_api = use_agent_api
        self._session = requests.Session()

    def parse_file(self, pdf_path: str, output_dir: str) -> Dict[str, Any]:
        """
        解析单个PDF文件

        Args:
            pdf_path: PDF文件路径
            output_dir: 输出目录

        Returns:
            解析结果字典
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")

        # 计算SHA1作为文件名
        sha1_name = self._compute_sha1(pdf_path)
        output_path = Path(output_dir) / f"{sha1_name}.json"

        # 如果已解析，直接返回
        if output_path.exists():
            return json.loads(output_path.read_text())

        # 获取页数，决定是否需要分页解析
        page_count = self._get_page_count(pdf_path)

        if page_count > 20:
            # 分页解析：每20页一组
            all_markdown_parts = []
            total_pages_in_result = 0

            for start_page in range(1, page_count + 1, 20):
                end_page = min(start_page + 19, page_count)
                part_output = output_path.parent / f"{sha1_name}_part_{start_page}.json"

                if part_output.exists():
                    # 已解析过，直接读取
                    part_data = json.loads(part_output.read_text())
                    all_markdown_parts.append(part_data["content"]["markdown"])
                    total_pages_in_result += part_data["metainfo"]["total_pages"]
                else:
                    # 上传并解析这一部分
                    task_id = self._upload_pdf(pdf_path, start_page, end_page)
                    result_url = self._wait_for_result(task_id, pdf_path.name)
                    # 记录实际解析的页数范围
                    actual_pages = end_page - start_page + 1
                    part_data = self._download_result(result_url, part_output, pdf_path.name, sha1_name, actual_pages)
                    all_markdown_parts.append(part_data["content"]["markdown"])
                    total_pages_in_result += actual_pages

            # 合并所有部分
            combined_markdown = "\n\n---\n\n".join(all_markdown_parts)
            combined_data = {
                "metainfo": {
                    "source": pdf_path.name,
                    "sha1_name": sha1_name,
                    "parser": "mineru",
                    "total_pages": total_pages_in_result
                },
                "content": {
                    "markdown": combined_markdown,
                    "pages": self._parse_markdown_to_pages(combined_markdown),
                    "tables": []
                }
            }
            output_path.write_text(json.dumps(combined_data, ensure_ascii=False, indent=2))
            return combined_data
        else:
            # 直接解析（页数 <= 20）
            task_id = self._upload_pdf(pdf_path, 1, page_count)
            result_url = self._wait_for_result(task_id, pdf_path.name)
            self._download_and_save(result_url, output_path, pdf_path.name, sha1_name, page_count)
            return json.loads(output_path.read_text())

    def parse_directory(self, pdf_dir: str, output_dir: str) -> List[Dict[str, Any]]:
        """批量解析目录中的PDF"""
        pdf_dir = Path(pdf_dir)
        pdf_files = list(pdf_dir.glob("*.pdf")) + list(pdf_dir.glob("*.PDF"))

        results = []
        for pdf_file in tqdm(pdf_files, desc="解析PDF"):
            try:
                result = self.parse_file(str(pdf_file), output_dir)
                results.append(result)
            except Exception as e:
                logger.error("解析失败 %s: %s", pdf_file.name, e)

        return results

    def _upload_pdf(self, pdf_path: Path, start_page: int = 1, end_page: int = None) -> str:
        """上传PDF文件，获取task_id

        Args:
            pdf_path: PDF文件路径
            start_page: 起始页（1-based）
            end_page: 结束页（1-based），超过20页的文档会分批解析
        """
        if end_page is None:
            end_page = 20 if start_page == 1 else start_page + 19

        if self.use_agent_api:
            # Agent API - 两步流程：1.获取签名URL 2.PUT上传文件
            # Step 1: 获取上传签名
            # 如果PDF页数超过20，需要分页解析
            page_count = self._get_page_count(pdf_path)
            self.current_pdf_page_count = page_count

            # page_range 参数（仅影响 Agent API 的 20 页限制）
            data = {
                "file_name": pdf_path.name,
                "language": "ch",
                "page_range": f"{start_page}-{end_page}"
            }

            resp = self._session.post(
                self.AGENT_API_URL.replace("/parse/url", "/parse/file"),
                json=data,
                timeout=30
            )

            if resp.status_code != 200:
                raise RuntimeError(f"获取上传URL失败: {resp.text}")

            resp_data = resp.json()
            if resp_data.get("code") != 0:
                raise RuntimeError(f"API错误: {resp_data.get('msg', resp.text)}")

            task_id = resp_data["data"]["task_id"]
            file_url = resp_data["data"]["file_url"]

            # Step 2: PUT上传文件（不指定Content-Type，让OSS自动处理）
            upload_resp = self._session.put(
                file_url,
                data=open(pdf_path, "rb"),
                timeout=120
            )

            if upload_resp.status_code not in (200, 201, 204):
                raise RuntimeError(f"文件上传失败: {upload_resp.status_code} {upload_resp.text}")

            return task_id
        else:
            # Precision API - 需要认证
            if not self.api_key:
                raise ValueError("使用Precision API需要设置MINERU_API_KEY")

            with open(pdf_path, "rb") as f:
                files = {"file": (pdf_path.name, f, "application/pdf")}
                headers = {"Authorization": f"Bearer {self.api_key}"}

                response = self._session.post(
                    self.PRECISION_API_URL,
                    files=files,
                    headers=headers,
                    timeout=60
                )

            if response.status_code != 200:
                raise RuntimeError(f"上传失败: {response.text}")

            return response.json()["data"]["task_id"]

    def _wait_for_result(self, task_id: str, filename: str, max_wait: int = 300) -> str:
        """
        轮询等待解析结果

        Returns:
            markdown_url - Markdown结果的URL
        """
        start_time = time.time()
        check_interval = 3  # 每3秒检查一次

        while time.time() - start_time < max_wait:
            try:
                response = self._session.get(
                    self.RESULT_URL.format(task_id=task_id),
                    timeout=30
                )

                if response.status_code != 200:
                    logger.warning("查询失败: %s", response.text)
                    time.sleep(check_interval)
                    continue

                result = response.json()
                state = result["data"]["state"]

                if state == "done":
                    return result["data"]["markdown_url"]
                elif state == "failed":
                    raise RuntimeError(f"解析失败: {result['data'].get('err_msg', '未知错误')}")

                # 进行中，继续等待
                time.sleep(check_interval)

            except Exception as e:
                logger.error("查询异常: %s", e)
                time.sleep(check_interval)

        raise TimeoutError(f"解析超时（{max_wait}秒）: {filename}")

    def _download_and_save(self, markdown_url: str, output_path: Path, filename: str, sha1_name: str, actual_pages: int = None):
        """下载Markdown结果并转换为标准JSON格式

        Args:
            actual_pages: 实际解析的页数
        """
        # 下载Markdown内容
        response = self._session.get(markdown_url, timeout=60)
        if response.status_code != 200:
            raise RuntimeError(f"下载失败: {response.text}")

        markdown_content = response.text

        # 如果没有传入actual_pages，则从markdown估算
        if actual_pages is None:
            actual_pages = self._count_pages(markdown_content)

        # 构建标准输出结构
        output_data = {
            "metainfo": {
                "source": filename,
                "sha1_name": sha1_name,
                "parser": "mineru",
                "total_pages": actual_pages
            },
            "content": {
                "markdown": markdown_content,
                "pages": self._parse_markdown_to_pages(markdown_content),
                "tables": []
            }
        }

        output_path.write_text(json.dumps(output_data, ensure_ascii=False, indent=2))

    def _download_result(self, markdown_url: str, output_path: Path, filename: str, sha1_name: str, actual_pages: int = None) -> Dict[str, Any]:
        """下载Markdown结果并保存（供分页解析使用）

        Args:
            actual_pages: 实际解析的页数（分页时传入，替代从markdown计算）
        """
        response = self._session.get(markdown_url, timeout=60)
        if response.status_code != 200:
            raise RuntimeError(f"下载失败: {response.text}")

        markdown_content = response.text

        # 如果没有传入actual_pages，则从markdown估算
        if actual_pages is None:
            actual_pages = self._count_pages(markdown_content)

        output_data = {
            "metainfo": {
                "source": filename,
                "sha1_name": sha1_name,
                "parser": "mineru",
                "total_pages": actual_pages,
                "page_range": f"{actual_pages}_pages"  # 记录这一块的页数
            },
            "content": {
                "markdown": markdown_content,
                "pages": self._parse_markdown_to_pages(markdown_content),
                "tables": []
            }
        }

        output_path.write_text(json.dumps(output_data, ensure_ascii=False, indent=2))
        return output_data

    def _count_pages(self, markdown_content: str) -> int:
        """统计页数（基于分隔符）"""
        return markdown_content.count("\n---\n") + 1

    def _get_page_count(self, pdf_path: Path) -> int:
        """获取PDF页数"""
        try:
            import fitz
            doc = fitz.open(pdf_path)
            count = len(doc)
            doc.close()
            return count
        except:
            return 0

    def _parse_markdown_to_pages(self, markdown_content: str) -> List[Dict[str, Any]]:
        """将Markdown解析为页面列表

        Note: MinerU API返回的markdown不包含页分隔符，
        因此只能将整个内容作为一个"块"处理，
        实际页数由 metainfo.total_pages 记录。
        """
        pages = []
        page_texts = markdown_content.split("\n---\n")

        # 如果没有分隔符（常见于MinerU返回），整个内容作为一页
        if len(page_texts) == 1 and page_texts[0] == markdown_content:
            pages.append({
                "page": 1,
                "text": markdown_content.strip(),
                "tables": []
            })
        else:
            for i, text in enumerate(page_texts, 1):
                if text.strip():
                    pages.append({
                        "page": i,
                        "text": text.strip(),
                        "tables": []
                    })

        return pages

    def _compute_sha1(self, file_path: Path) -> str:
        """计算文件SHA1"""
        sha1 = hashlib.sha1()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha1.update(chunk)
        return sha1.hexdigest()[:16]


class PDFParser:
    """PDF解析器 - 使用MinerU API"""

    def __init__(self, config: Optional[PDFConfig] = None):
        self.config = config or PDFConfig()
        api_key = os.getenv("MINERU_API_KEY", "")
        # 优先使用Agent API（无需积分），Precision API作为备选
        self.client = MinerUAPI(api_key=api_key, use_agent_api=True)

    def parse_file(self, pdf_path: str, output_dir: str) -> Dict[str, Any]:
        """解析单个PDF文件"""
        return self.client.parse_file(pdf_path, output_dir)

    def parse_directory(self, pdf_dir: str, output_dir: str) -> List[Dict[str, Any]]:
        """批量解析目录中的PDF"""
        return self.client.parse_directory(pdf_dir, output_dir)


def parse_pdfs_cli():
    """CLI入口"""
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("用法: python pdf_mineru.py <pdf_dir> [output_dir]")
        sys.exit(1)

    pdf_dir = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "data/parsed"

    parser = PDFParser()
    results = parser.parse_directory(pdf_dir, output_dir)
    logger.info("解析完成: %d 个文件", len(results))


if __name__ == "__main__":
    parse_pdfs_cli()