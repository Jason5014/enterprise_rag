"""后端配置 — 从 .env / 环境变量读取"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# 项目根目录（backend/ 上两级）
ROOT_DIR = Path(__file__).parent.parent.parent

# JWT
SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24h

# 数据目录
DATA_DIR: Path = ROOT_DIR / "data"
DB_PATH: str = str(DATA_DIR / "kb.db")

# Admin 账号（首次启动自动创建）
ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")

# CORS 允许的来源（开发时放开前端端口）
CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
