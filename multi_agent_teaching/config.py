"""
多智能体教学地图配置 —— 从主应用 config 读取，不再使用独立 .env
"""
import sys as _sys
import os as _os
import importlib as _importlib

def _load_main_config():
    """导入主应用的 config 模块（向上一层目录）"""
    _main_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    if _main_dir not in _sys.path:
        _sys.path.insert(0, _main_dir)
    return _importlib.import_module("config")

_main = _load_main_config()

LLM_BASE_URL = getattr(_main, "TEACHING_MAP_LLM_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = getattr(_main, "TEACHING_MAP_LLM_API_KEY", "")
LLM_MODEL_NAME = getattr(_main, "TEACHING_MAP_LLM_MODEL_NAME", "gpt-4o")

MAX_VALIDATION_RETRIES = getattr(_main, "TEACHING_MAP_MAX_VALIDATION_RETRIES", 3)
MAIN_FULL_RECHECK_INTERVAL = getattr(_main, "TEACHING_MAP_MAIN_FULL_RECHECK_INTERVAL", 2)

from urllib.parse import urlparse as _urlparse
_parsed = _urlparse(getattr(_main, "SQLALCHEMY_DATABASE_URI", ""))
MYSQL_HOST = _parsed.hostname or "127.0.0.1"
MYSQL_PORT = _parsed.port or 3306
MYSQL_USER = _parsed.username or "root"
MYSQL_PASSWORD = _parsed.password or ""
MYSQL_DB = getattr(_main, "TEACHING_MAP_MYSQL_DB", "teaching_maps")
