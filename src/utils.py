"""公共工具函数"""
import os
from typing import Optional


def get_api_key(env_var: str = "DASHSCOPE_API_KEY") -> str:
    """从环境变量获取 API 密钥（调用前应已 load_dotenv）"""
    key = os.getenv(env_var, "")
    placeholder = f"your_{env_var.lower()}_here"
    if not key or key == placeholder:
        raise ValueError(f"请在 .env 中设置 {env_var}")
    return key
