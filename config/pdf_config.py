"""PDF解析配置"""
from dataclasses import dataclass
from .settings import BaseConfig


@dataclass
class PDFConfig(BaseConfig):
    """PDF解析相关配置"""

    # MinerU配置
    parse_tables: bool = True  # 是否解析表格
    extract_images: bool = False  # 是否提取图片描述
    page_range: str = "all"  # 解析页码范围，"all"或"start-end"
    output_format: str = "json"  # 输出格式

    # 表格序列化配置
    serialization_model: str = "qwen-turbo"  # 序列化模型
    serialization_batch_size: int = 5  # 批量处理大小
    max_workers: int = 3  # 并行工作数

    def validate(self) -> bool:
        """验证配置合法性"""
        if self.page_range != "all":
            if "-" not in self.page_range:
                raise ValueError("page_range must be 'all' or 'start-end' format")
            try:
                start, end = self.page_range.split("-")
                if int(start) <= 0 or int(end) <= 0:
                    raise ValueError("page numbers must be positive")
                if int(start) > int(end):
                    raise ValueError("start page must be less than end page")
            except ValueError:
                raise ValueError("invalid page_range format")
        return True
