"""PDF解析模块测试"""
import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


class TestPDFConfig:
    """PDFConfig测试"""

    def test_pdf_config_defaults(self):
        """测试默认配置"""
        from config.pdf_config import PDFConfig

        config = PDFConfig()
        assert config.parse_tables is True
        assert config.extract_images is False
        assert config.page_range == "all"
        assert config.output_format == "json"

    def test_pdf_config_validation(self):
        """测试配置验证"""
        from config.pdf_config import PDFConfig

        config = PDFConfig()
        assert config.validate() is True

    def test_pdf_config_invalid_page_range(self):
        """测试无效页码范围"""
        from config.pdf_config import PDFConfig

        config = PDFConfig(page_range="invalid")
        with pytest.raises(ValueError):
            config.validate()

    def test_pdf_config_valid_page_range(self):
        """测试有效页码范围"""
        from config.pdf_config import PDFConfig

        config = PDFConfig(page_range="1-10")
        assert config.validate() is True


class TestMinerUAPI:
    """MinerU API测试"""

    def test_api_init_without_key(self):
        """测试API初始化"""
        from src.pdf_mineru import MinerUAPI

        api = MinerUAPI(api_key=None, use_agent_api=True)
        assert api.api_key == ""
        assert api.use_agent_api is True

    def test_api_init_with_key(self):
        """测试API初始化带key"""
        from src.pdf_mineru import MinerUAPI

        api = MinerUAPI(api_key="test_key", use_agent_api=False)
        assert api.api_key == "test_key"
        assert api.use_agent_api is False

    @patch('src.pdf_mineru.requests.Session')
    def test_upload_pdf_agent_api(self, mock_session):
        """测试上传PDF（Agent API）"""
        from src.pdf_mineru import MinerUAPI

        mock_instance = MagicMock()
        mock_session.return_value = mock_instance

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"task_id": "test_task_123"}}
        mock_instance.post.return_value = mock_response

        api = MinerUAPI(api_key=None, use_agent_api=True)

        # 创建临时PDF文件
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"fake pdf content")
            temp_path = Path(f.name)

        try:
            task_id = api._upload_pdf(temp_path)
            assert task_id == "test_task_123"
        finally:
            temp_path.unlink()

    def test_compute_sha1(self):
        """测试SHA1计算"""
        import tempfile
        from src.pdf_mineru import MinerUAPI

        api = MinerUAPI()

        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            temp_path = Path(f.name)

        try:
            sha1 = api._compute_sha1(temp_path)
            assert len(sha1) == 16
            assert isinstance(sha1, str)
        finally:
            temp_path.unlink()

    def test_parse_markdown_to_pages(self):
        """测试Markdown解析为页面"""
        from src.pdf_mineru import MinerUAPI

        api = MinerUAPI()

        markdown = """# 第一页
内容1

---
# 第二页
内容2

---
# 第三页
内容3"""

        pages = api._parse_markdown_to_pages(markdown)

        assert len(pages) == 3
        assert pages[0]["page"] == 1
        assert "第一页" in pages[0]["text"]
        assert pages[1]["page"] == 2
        assert pages[2]["page"] == 3

    def test_count_pages(self):
        """测试页数统计"""
        from src.pdf_mineru import MinerUAPI

        api = MinerUAPI()

        markdown = "第一页\n---\n第二页\n---\n第三页"
        assert api._count_pages(markdown) == 3

        markdown_empty = ""
        assert api._count_pages(markdown_empty) == 1


class TestPDFParser:
    """PDFParser测试"""

    def test_parser_init(self):
        """测试解析器初始化"""
        from src.pdf_mineru import PDFParser
        from config.pdf_config import PDFConfig

        config = PDFConfig()
        parser = PDFParser(config=config)
        assert parser.config == config
        assert parser.client is not None


class TestIntegration:
    """集成测试"""

    def test_mineru_api_url(self):
        """测试API URL配置"""
        from src.pdf_mineru import MinerUAPI

        api = MinerUAPI()
        assert "mineru.net" in api.AGENT_API_URL
        assert "mineru.net" in api.RESULT_URL

    def test_http_client_available(self):
        """测试HTTP客户端是否可用"""
        try:
            import requests
            assert True
        except ImportError:
            assert False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])