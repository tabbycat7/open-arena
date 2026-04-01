"""
统一配置模块
从 .env 文件加载所有配置项（数据库、大模型 API 等）
"""

import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


# ===================== 数据库配置 =====================
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "123456")
DB_NAME = os.getenv("DB_NAME", "open_arena")

SQLALCHEMY_DATABASE_URI = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
)
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ENGINE_OPTIONS = {"pool_recycle": 3600}


# ===================== 大模型 API 配置 =====================
# 加持模型（润色教师观点）
ENHANCE_MODEL_API_KEY = os.getenv("ENHANCE_MODEL_API_KEY", "")
ENHANCE_MODEL_API_URL = os.getenv("ENHANCE_MODEL_API_URL", "https://api.openai.com/v1/chat/completions")
ENHANCE_MODEL_NAME = os.getenv("ENHANCE_MODEL_NAME", "gpt-4")

# 反驳模型（反驳教师观点）
REBUT_MODEL_API_KEY = os.getenv("REBUT_MODEL_API_KEY", "")
REBUT_MODEL_API_URL = os.getenv("REBUT_MODEL_API_URL", "https://api.openai.com/v1/chat/completions")
REBUT_MODEL_NAME = os.getenv("REBUT_MODEL_NAME", "gpt-4")
