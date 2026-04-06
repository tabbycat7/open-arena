"""
统一配置模块
从 .env 文件加载所有配置项（数据库、大模型 API 等）
"""

import json
import os
from dotenv import load_dotenv


def _model_display_name(model_id: str) -> str:
    parts = [p for p in (model_id or "").split("/") if p]
    return parts[-1] if parts else model_id


def _normalize_model_options(raw_options, default_icon: str) -> list:
    normalized = []
    seen = set()
    for item in raw_options:
        if not isinstance(item, dict):
            continue

        model_id = str(item.get("id", "")).strip()
        if not model_id or model_id in seen:
            continue

        label = str(item.get("name", "")).strip() or _model_display_name(model_id)
        icon = str(item.get("icon", "")).strip().lstrip("/") or default_icon

        normalized.append({"id": model_id, "name": label, "icon": icon})
        seen.add(model_id)

    return normalized


def _get_env_int(name: str, default: int) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_env_float(name: str, default: float) -> float:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default

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
ENHANCE_MODEL_API_URL = os.getenv("ENHANCE_MODEL_API_URL", "https://aihubmix.com/v1/chat/completions")
ENHANCE_MODEL_API_KEY = os.getenv("ENHANCE_MODEL_API_KEY", "")
ENHANCE_MODEL_NAME = os.getenv("ENHANCE_MODEL_NAME", "gemini-3-flash-preview")

# 反驳模型（反驳学生观点）
REFUTE_MODEL_API_URL = os.getenv("REFUTE_MODEL_API_URL", "https://aihubmix.com/v1/chat/completions")
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
        "gemini-2.5-flash-preview,gpt-4o-mini,deepseek-v3,claude-3-5-haiku-20241022,qwen-turbo"
    ).split(",")
    if m.strip()
]


# ===================== 多智能体教学地图配置 =====================
TEACHING_MAP_LLM_BASE_URL = os.getenv("TEACHING_MAP_LLM_BASE_URL", "https://aihubmix.com/v1")
TEACHING_MAP_LLM_API_KEY = os.getenv("TEACHING_MAP_LLM_API_KEY", "") or os.getenv("ARK_API_KEY", "")
TEACHING_MAP_LLM_MODEL_NAME = os.getenv("TEACHING_MAP_LLM_MODEL_NAME", "deepseek-reasoner")
TEACHING_MAP_LLM_MAX_TOKENS = _get_env_int("TEACHING_MAP_LLM_MAX_TOKENS", 8192)
if TEACHING_MAP_LLM_MAX_TOKENS < 1:
    TEACHING_MAP_LLM_MAX_TOKENS = 8192
TEACHING_MAP_GENERATOR_MODEL_NAME = os.getenv(
    "TEACHING_MAP_GENERATOR_MODEL_NAME",
    TEACHING_MAP_LLM_MODEL_NAME,
)
TEACHING_MAP_VALIDATOR_MODEL_NAME = os.getenv(
    "TEACHING_MAP_VALIDATOR_MODEL_NAME",
    "deepseek-chat",
)
TEACHING_MAP_SELECTABLE_MODEL_IDS = [
    m.strip()
    for m in os.getenv(
        "TEACHING_MAP_SELECTABLE_MODEL_IDS",
        "gpt-5.4-high,gpt-5.4,gpt-5.4-low,claude-opus-4-6-think,claude-opus-4-6,gemini-3.1-pro-preview,gemini-3.1-flash-lite-preview,gemma-4-31b-it,kimi-k2.5,qwen3.6-plus,doubao-seed-2-0-pro",
    ).split(",")
    if m.strip()
]
TEACHING_MAP_DEFAULT_MODEL_ICON = os.getenv(
    "TEACHING_MAP_DEFAULT_MODEL_ICON",
    "images/model-icons/model-default.svg",
).strip().lstrip("/")
_DEFAULT_TEACHING_MAP_MODEL_ICON_MAP = {
    "gpt-5.4-high": "images/model-icons/gpt.svg",
    "gpt-5.4": "images/model-icons/gpt.svg",
    "gpt-5.4-low": "images/model-icons/gpt.svg",
    "claude-opus-4-6-think": "images/model-icons/claude.svg",
    "claude-opus-4-6": "images/model-icons/claude.svg",
    "gemini-3.1-pro-preview": "images/model-icons/google.svg",
    "gemini-3.1-flash-lite-preview": "images/model-icons/google.svg",
    "gemma-4-31b-it": "images/model-icons/google.svg",
    "kimi-k2.5": "images/model-icons/kimi.svg",
    "qwen3.6-plus": "images/model-icons/qwen.svg",
    "doubao-seed-2-0-pro": "images/model-icons/doubao.svg",
}
TEACHING_MAP_MODEL_ICON_MAP = dict(_DEFAULT_TEACHING_MAP_MODEL_ICON_MAP)
_icon_map_raw = os.getenv("TEACHING_MAP_MODEL_ICON_MAP", "").strip()
if _icon_map_raw:
    try:
        _icon_map_custom = json.loads(_icon_map_raw)
        if isinstance(_icon_map_custom, dict):
            for _model_id, _icon_path in _icon_map_custom.items():
                if not isinstance(_model_id, str) or not isinstance(_icon_path, str):
                    continue
                _model_id = _model_id.strip()
                _icon_path = _icon_path.strip().lstrip("/")
                if _model_id and _icon_path:
                    TEACHING_MAP_MODEL_ICON_MAP[_model_id] = _icon_path
    except json.JSONDecodeError:
        pass

_model_options_raw = os.getenv("TEACHING_MAP_MODEL_OPTIONS", "").strip()
if _model_options_raw:
    try:
        _model_options_loaded = json.loads(_model_options_raw)
        if isinstance(_model_options_loaded, list):
            TEACHING_MAP_MODEL_OPTIONS = _normalize_model_options(
                _model_options_loaded,
                TEACHING_MAP_DEFAULT_MODEL_ICON,
            )
        else:
            TEACHING_MAP_MODEL_OPTIONS = []
    except json.JSONDecodeError:
        TEACHING_MAP_MODEL_OPTIONS = []
else:
    TEACHING_MAP_MODEL_OPTIONS = []

if not TEACHING_MAP_MODEL_OPTIONS:
    TEACHING_MAP_MODEL_OPTIONS = []
    _seen_model_ids = set()
    for _raw_model_id in TEACHING_MAP_SELECTABLE_MODEL_IDS:
        _model_id = str(_raw_model_id or "").strip()
        if not _model_id or _model_id in _seen_model_ids:
            continue
        _seen_model_ids.add(_model_id)
        _icon_path = TEACHING_MAP_MODEL_ICON_MAP.get(_model_id, TEACHING_MAP_DEFAULT_MODEL_ICON)
        TEACHING_MAP_MODEL_OPTIONS.append(
            {
                "id": _model_id,
                "name": _model_display_name(_model_id),
                "icon": str(_icon_path or TEACHING_MAP_DEFAULT_MODEL_ICON).strip().lstrip("/"),
            }
        )

TEACHING_MAP_DEFAULT_TEMPERATURE = _get_env_float("TEACHING_MAP_DEFAULT_TEMPERATURE", 0.7)
if TEACHING_MAP_DEFAULT_TEMPERATURE < 0:
    TEACHING_MAP_DEFAULT_TEMPERATURE = 0.0
elif TEACHING_MAP_DEFAULT_TEMPERATURE > 2:
    TEACHING_MAP_DEFAULT_TEMPERATURE = 2.0

_DEFAULT_TEACHING_MAP_FIXED_TEMPERATURE_MODELS = {
    "claude-opus-4-6-think": 1.0,
}
TEACHING_MAP_FIXED_TEMPERATURE_MODELS = dict(_DEFAULT_TEACHING_MAP_FIXED_TEMPERATURE_MODELS)
_fixed_temperature_raw = os.getenv("TEACHING_MAP_FIXED_TEMPERATURE_MODELS", "").strip()
if _fixed_temperature_raw:
    try:
        _fixed_temperature_custom = json.loads(_fixed_temperature_raw)
        if isinstance(_fixed_temperature_custom, dict):
            for _model_id, _temperature in _fixed_temperature_custom.items():
                if not isinstance(_model_id, str):
                    continue
                _model_id = _model_id.strip()
                if not _model_id:
                    continue
                try:
                    _temp_value = float(_temperature)
                except (TypeError, ValueError):
                    continue
                if 0.0 <= _temp_value <= 2.0:
                    TEACHING_MAP_FIXED_TEMPERATURE_MODELS[_model_id] = _temp_value
    except json.JSONDecodeError:
        pass

TEACHING_MAP_IMAGE_PARSER_MODEL_NAME = os.getenv(
    "TEACHING_MAP_IMAGE_PARSER_MODEL_NAME",
    TEACHING_MAP_GENERATOR_MODEL_NAME,
)
TEACHING_MAP_MAX_VALIDATION_RETRIES = int(os.getenv("TEACHING_MAP_MAX_VALIDATION_RETRIES", "3"))
TEACHING_MAP_MYSQL_DB = os.getenv("TEACHING_MAP_MYSQL_DB", "teaching_maps")

# agents 子包内部 `from config import ...` 时使用的别名
LLM_BASE_URL = TEACHING_MAP_LLM_BASE_URL
LLM_API_KEY = TEACHING_MAP_LLM_API_KEY
LLM_MODEL_NAME = TEACHING_MAP_LLM_MODEL_NAME
LLM_MAX_TOKENS = TEACHING_MAP_LLM_MAX_TOKENS
LLM_GENERATOR_MODEL_NAME = TEACHING_MAP_GENERATOR_MODEL_NAME
LLM_VALIDATOR_MODEL_NAME = TEACHING_MAP_VALIDATOR_MODEL_NAME
LLM_MODEL_OPTIONS = TEACHING_MAP_MODEL_OPTIONS
LLM_SELECTABLE_MODEL_IDS = TEACHING_MAP_SELECTABLE_MODEL_IDS
LLM_DEFAULT_MODEL_ICON = TEACHING_MAP_DEFAULT_MODEL_ICON
LLM_MODEL_ICON_MAP = TEACHING_MAP_MODEL_ICON_MAP
LLM_DEFAULT_TEMPERATURE = TEACHING_MAP_DEFAULT_TEMPERATURE
LLM_FIXED_TEMPERATURE_MODELS = TEACHING_MAP_FIXED_TEMPERATURE_MODELS
LLM_IMAGE_PARSER_MODEL_NAME = TEACHING_MAP_IMAGE_PARSER_MODEL_NAME
MAX_VALIDATION_RETRIES = TEACHING_MAP_MAX_VALIDATION_RETRIES
