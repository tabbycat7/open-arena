"""
多智能体教学地图配置 —— 从主应用 config 读取，不再使用独立 .env
"""
import sys as _sys
import os as _os
import importlib as _importlib
import importlib.util as _importlib_util

def _load_main_config():
    """按绝对路径加载主应用根目录 config.py，避免路径顺序导致自导入。"""
    _main_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    _main_config_path = _os.path.join(_main_dir, "config.py")
    _spec = _importlib_util.spec_from_file_location("open_arena_main_config", _main_config_path)
    if _spec is None or _spec.loader is None:
        raise ImportError("Cannot load root config.py")

    _module = _importlib_util.module_from_spec(_spec)
    _spec.loader.exec_module(_module)
    return _module

_main = _load_main_config()

LLM_BASE_URL = getattr(_main, "TEACHING_MAP_LLM_BASE_URL", "https://aihubmix.com/v1")
LLM_API_KEY = getattr(_main, "TEACHING_MAP_LLM_API_KEY", "")
LLM_MODEL_NAME = getattr(_main, "TEACHING_MAP_LLM_MODEL_NAME", "gpt-4o")
LLM_MAX_TOKENS = int(getattr(_main, "TEACHING_MAP_LLM_MAX_TOKENS", 8192))
LLM_GENERATOR_MODEL_NAME = getattr(_main, "TEACHING_MAP_GENERATOR_MODEL_NAME", LLM_MODEL_NAME)
LLM_VALIDATOR_MODEL_NAME = getattr(_main, "TEACHING_MAP_VALIDATOR_MODEL_NAME", "deepseek-chat")
LLM_MODEL_OPTIONS = list(getattr(_main, "TEACHING_MAP_MODEL_OPTIONS", []))
LLM_SELECTABLE_MODEL_IDS = list(getattr(_main, "TEACHING_MAP_SELECTABLE_MODEL_IDS", []))
LLM_DEFAULT_MODEL_ICON = getattr(
    _main,
    "TEACHING_MAP_DEFAULT_MODEL_ICON",
    "images/model-icons/model-default.svg",
)
LLM_MODEL_ICON_MAP = dict(getattr(_main, "TEACHING_MAP_MODEL_ICON_MAP", {}))
LLM_IMAGE_PARSER_MODEL_NAME = getattr(
    _main,
    "TEACHING_MAP_IMAGE_PARSER_MODEL_NAME",
    LLM_GENERATOR_MODEL_NAME,
)

MAX_VALIDATION_RETRIES = getattr(_main, "TEACHING_MAP_MAX_VALIDATION_RETRIES", 3)

from urllib.parse import urlparse as _urlparse
_parsed = _urlparse(getattr(_main, "SQLALCHEMY_DATABASE_URI", ""))
MYSQL_HOST = _parsed.hostname or "127.0.0.1"
MYSQL_PORT = _parsed.port or 3306
MYSQL_USER = _parsed.username or "root"
MYSQL_PASSWORD = _parsed.password or ""
MYSQL_DB = getattr(_main, "TEACHING_MAP_MYSQL_DB", "teaching_maps")
