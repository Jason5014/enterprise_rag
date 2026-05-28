"""表格序列化模块 - 将HTML表格转换为文本描述"""
import os
import json
import re
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from tqdm import tqdm

logger = logging.getLogger(__name__)

try:
    import dashscope
    from dashscope import Generation
    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False

from config.pdf_config import PDFConfig


class TableSerializer:
    """表格序列化器 - 将HTML表格转换为LLM可读的文本"""

    SYSTEM_PROMPT = """你是一个表格内容提取专家。你的任务是将HTML表格转换为简洁的文本描述。

输入是一个HTML表格，你需要提取其中的关键信息并用结构化文本描述。

输出格式要求：
- 产品/指标 名称: 值 | 属性1: 值 | 属性2: 值
- 每个表格行用"|"分隔
- 保持数值和单位的准确性
- 如果有表头，说明表头含义

示例：
输入: <table><tr><th>产品</th><th>营收</th><th>增长</th></tr><tr><td>A产品</td><td>100万</td><td>20%</td></tr></table>
输出: 产品: A产品 | 营收: 100万 | 增长: 20%
"""

    USER_PROMPT_TEMPLATE = """请将以下HTML表格转换为文本描述：

{table_html}

只输出转换后的文本描述，不要其他解释。"""

    def __init__(self, config: Optional[PDFConfig] = None):
        self.config = config or PDFConfig()
        if DASHSCOPE_AVAILABLE:
            self.api_key = self._get_api_key()

    def _get_api_key(self) -> str:
        """获取API密钥"""
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("DASHSCOPE_API_KEY", "")
        if not api_key or api_key == "your_dashscope_api_key_here":
            raise ValueError("请在.env中设置DASHSCOPE_API_KEY")
        return api_key

    def serialize_html(self, html_table: str) -> str:
        """将HTML表格转换为文本描述"""
        if not DASHSCOPE_AVAILABLE:
            return self._simple_serialize(html_table)

        try:
            response = Generation.call(
                model=self.config.serialization_model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": self.USER_PROMPT_TEMPLATE.format(table_html=html_table)}
                ],
                api_key=self.api_key
            )

            if response.status_code == 200:
                return response.output.get("text", "").strip()
            else:
                return self._simple_serialize(html_table)
        except Exception as e:
            logger.error("表格序列化失败: %s", e)
            return self._simple_serialize(html_table)

    def serialize_batch(self, tables: List[Dict[str, Any]], max_workers: int = 3) -> List[Dict[str, Any]]:
        """批量序列化表格"""
        results = []
        for table in tqdm(tables, desc="序列化表格"):
            serialized = self.serialize_html(table.get("html", ""))
            results.append({
                "table_id": table.get("table_id"),
                "page": table.get("page"),
                "original_html": table.get("html", ""),
                "serialized_text": serialized
            })
        return results

    def _simple_serialize(self, html_table: str) -> str:
        """简单的HTML表格转文本（不调用API）"""
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', ' ', html_table)
        # 清理多余空格
        text = re.sub(r'\s+', ' ', text)
        # 移除&nbsp;
        text = text.replace('&nbsp;', ' ')
        # 移除多余空格
        text = re.sub(r' +', ' ', text).strip()
        return text

    def process_parsed_report(self, parsed_json_path: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        """处理已解析的报告JSON，提取并序列化HTML表格"""
        with open(parsed_json_path, 'r', encoding='utf-8') as f:
            report = json.load(f)

        markdown = report.get("content", {}).get("markdown", "")

        # 从 markdown 中提取所有 HTML 表格
        html_tables = re.findall(r'<table[^>]*>.*?</table>', markdown, re.DOTALL | re.IGNORECASE)

        if not html_tables:
            return report

        logger.info("发现 %d 个 HTML 表格", len(html_tables))

        # 序列化每个表格
        serialized_map = {}
        for i, html_table in enumerate(html_tables):
            serialized = self.serialize_html(html_table)
            serialized_map[html_table] = serialized

        # 替换 markdown 中的 HTML 表格为序列化文本
        for html_table, serialized in serialized_map.items():
            # 用标签包裹序列化后的文本，便于后续处理
            markdown = markdown.replace(html_table, f"\n<!-- TABLE_SERIALIZED_{i} -->\n{serialized}\n<!-- END_TABLE_{i} -->\n")

        # 保存回 report
        report["content"]["markdown"] = markdown

        # 保存更新后的报告
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

        return report