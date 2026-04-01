"""
统一配置模块
从 .env 文件加载所有配置项（数据库、大模型 API 等）
"""

import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


# ===================== 应用配置 =====================
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")


# ===================== 数据库配置 =====================
SQLALCHEMY_DATABASE_URI = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:371619@localhost:3306/open_arena?charset=utf8mb4",
)
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ENGINE_OPTIONS = {"pool_recycle": 3600}


# ===================== 大模型 API 配置 =====================
# 加持模型（润色学生观点）
ENHANCE_MODEL_API_URL = os.getenv("ENHANCE_MODEL_API_URL", "https://ssvip.dmxapi.com/v1/chat/completions")
ENHANCE_MODEL_API_KEY = os.getenv("ENHANCE_MODEL_API_KEY", "")
ENHANCE_MODEL_NAME = os.getenv("ENHANCE_MODEL_NAME", "gemini-3-flash-preview")

# 反驳模型（反驳学生观点）
REFUTE_MODEL_API_URL = os.getenv("REFUTE_MODEL_API_URL", "https://ssvip.dmxapi.com/v1/chat/completions")
REFUTE_MODEL_API_KEY = os.getenv("REFUTE_MODEL_API_KEY", "")
# 反驳模型名称列表（随机抽取一个用于整个辩论会话，保持会话内模型一致）
REFUTE_MODEL_NAMES = [
    m.strip()
    for m in os.getenv("REFUTE_MODEL_NAMES", "gemini-3-flash-preview").split(",")
    if m.strip()
]


# ===================== 教案设计竞技场配置 =====================
LESSON_MODEL_API_URL = os.getenv("LESSON_MODEL_API_URL", ENHANCE_MODEL_API_URL)
LESSON_MODEL_API_KEY = os.getenv("LESSON_MODEL_API_KEY", "") or ENHANCE_MODEL_API_KEY
LESSON_MODEL_NAMES = [
    m.strip()
    for m in os.getenv(
        "LESSON_MODEL_NAMES",
    ).split(",")
    if m.strip()
]
