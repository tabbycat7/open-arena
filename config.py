"""
统一配置模块
从 .env 文件加载所有配置项（数据库、大模型 API 等）
"""

import json
import os
from dotenv import load_dotenv


def _get_env_int(name: str, default: int) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _build_default_thinking_budget_presets(min_budget: int, max_budget: int) -> list:
    if max_budget <= min_budget:
        return [
            {
                "id": "medium",
                "label": "中",
                "min": min_budget,
                "max": max_budget,
                "budget": min_budget,
            }
        ]

    target_ranges = [
        ("ultra_low", "超低", min_budget, min(256, max_budget)),
        ("low", "低", max(min_budget, 256), min(512, max_budget)),
        ("medium", "中", max(min_budget, 512), min(2048, max_budget)),
        ("high", "高", max(min_budget, 2048), min(8192, max_budget)),
        ("ultra_high", "超高", max(min_budget, 8192), max_budget),
    ]

    presets = []
    for preset_id, label, start, end in target_ranges:
        if end < start:
            continue
        presets.append(
            {
                "id": preset_id,
                "label": label,
                "min": start,
                "max": end,
                "budget": (start + end) // 2,
            }
        )

    if presets:
        return presets

    return [
        {
            "id": "medium",
            "label": "中",
            "min": min_budget,
            "max": max_budget,
            "budget": (min_budget + max_budget) // 2,
        }
    ]


def _normalize_thinking_budget_presets(raw_presets, min_budget: int, max_budget: int) -> list:
    presets = []
    seen_ids = set()
    for item in raw_presets:
        if not isinstance(item, dict):
            continue

        preset_id = str(item.get("id", "")).strip()
        if not preset_id or preset_id in seen_ids:
            continue

        label = str(item.get("label", "")).strip() or preset_id
        try:
            range_min = int(item.get("min", min_budget))
        except (TypeError, ValueError):
            range_min = min_budget
        try:
            range_max = int(item.get("max", max_budget))
        except (TypeError, ValueError):
            range_max = max_budget
        if range_min > range_max:
            range_min, range_max = range_max, range_min

        range_min = max(min_budget, min(range_min, max_budget))
        range_max = max(min_budget, min(range_max, max_budget))
        if range_max < range_min:
            range_max = range_min

        try:
            budget = int(item.get("budget", (range_min + range_max) // 2))
        except (TypeError, ValueError):
            budget = (range_min + range_max) // 2
        budget = max(range_min, min(budget, range_max))

        presets.append(
            {
                "id": preset_id,
                "label": label,
                "min": range_min,
                "max": range_max,
                "budget": budget,
            }
        )
        seen_ids.add(preset_id)
    return presets


def _resolve_default_thinking_budget_preset(presets: list, default_budget: int, configured_id: str) -> str:
    if configured_id and any(item.get("id") == configured_id for item in presets):
        return configured_id

    for item in presets:
        if int(item["min"]) <= default_budget <= int(item["max"]):
            return str(item["id"])

    if presets:
        nearest = min(presets, key=lambda item: abs(int(item["budget"]) - default_budget))
        return str(nearest["id"])
    return ""

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
        "gemini-2.5-flash-preview,gpt-4o-mini,deepseek-v3,claude-3-5-haiku-20241022,qwen-turbo"
    ).split(",")
    if m.strip()
]


# ===================== 多智能体教学地图配置 =====================
TEACHING_MAP_LLM_BASE_URL = os.getenv("TEACHING_MAP_LLM_BASE_URL", "https://api.deepseek.com")
TEACHING_MAP_LLM_API_KEY = os.getenv("TEACHING_MAP_LLM_API_KEY", "") or os.getenv("ARK_API_KEY", "")
TEACHING_MAP_LLM_MODEL_NAME = os.getenv("TEACHING_MAP_LLM_MODEL_NAME", "deepseek-reasoner")
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
        "Pro/MiniMaxAI/MiniMax-M2.5,Pro/zai-org/GLM-5,Qwen/Qwen3.5-397B-A17B,Pro/deepseek-ai/DeepSeek-R1,moonshotai/Kimi-K2-Thinking",
    ).split(",")
    if m.strip()
]
TEACHING_MAP_THINKING_SUPPORTED_MODEL_IDS = [
    m.strip()
    for m in os.getenv(
        "TEACHING_MAP_THINKING_SUPPORTED_MODEL_IDS",
        "Pro/zai-org/GLM-5,deepseek-ai/DeepSeek-V3.2,Qwen/Qwen3.5-397B-A17B",
    ).split(",")
    if m.strip()
]
TEACHING_MAP_THINKING_DEFAULT_ENABLED = (
    os.getenv("TEACHING_MAP_THINKING_DEFAULT_ENABLED", "0").strip().lower()
    in {"1", "true", "yes", "on"}
)
TEACHING_MAP_THINKING_BUDGET_MIN = _get_env_int("TEACHING_MAP_THINKING_BUDGET_MIN", 128)
TEACHING_MAP_THINKING_BUDGET_MAX = _get_env_int("TEACHING_MAP_THINKING_BUDGET_MAX", 32768)
TEACHING_MAP_THINKING_BUDGET_DEFAULT = _get_env_int("TEACHING_MAP_THINKING_BUDGET_DEFAULT", 4096)
if TEACHING_MAP_THINKING_BUDGET_MIN < 1:
    TEACHING_MAP_THINKING_BUDGET_MIN = 1
if TEACHING_MAP_THINKING_BUDGET_MAX < TEACHING_MAP_THINKING_BUDGET_MIN:
    TEACHING_MAP_THINKING_BUDGET_MAX = TEACHING_MAP_THINKING_BUDGET_MIN
if TEACHING_MAP_THINKING_BUDGET_DEFAULT < TEACHING_MAP_THINKING_BUDGET_MIN:
    TEACHING_MAP_THINKING_BUDGET_DEFAULT = TEACHING_MAP_THINKING_BUDGET_MIN
if TEACHING_MAP_THINKING_BUDGET_DEFAULT > TEACHING_MAP_THINKING_BUDGET_MAX:
    TEACHING_MAP_THINKING_BUDGET_DEFAULT = TEACHING_MAP_THINKING_BUDGET_MAX
_default_thinking_budget_presets = _build_default_thinking_budget_presets(
    TEACHING_MAP_THINKING_BUDGET_MIN,
    TEACHING_MAP_THINKING_BUDGET_MAX,
)
_thinking_budget_presets_raw = (os.getenv("TEACHING_MAP_THINKING_BUDGET_PRESETS", "") or "").strip()
if _thinking_budget_presets_raw:
    try:
        _thinking_budget_presets_loaded = json.loads(_thinking_budget_presets_raw)
        if isinstance(_thinking_budget_presets_loaded, list):
            _custom_thinking_budget_presets = _normalize_thinking_budget_presets(
                _thinking_budget_presets_loaded,
                TEACHING_MAP_THINKING_BUDGET_MIN,
                TEACHING_MAP_THINKING_BUDGET_MAX,
            )
            TEACHING_MAP_THINKING_BUDGET_PRESETS = (
                _custom_thinking_budget_presets or _default_thinking_budget_presets
            )
        else:
            TEACHING_MAP_THINKING_BUDGET_PRESETS = _default_thinking_budget_presets
    except json.JSONDecodeError:
        TEACHING_MAP_THINKING_BUDGET_PRESETS = _default_thinking_budget_presets
else:
    TEACHING_MAP_THINKING_BUDGET_PRESETS = _default_thinking_budget_presets

TEACHING_MAP_THINKING_BUDGET_DEFAULT_PRESET = _resolve_default_thinking_budget_preset(
    TEACHING_MAP_THINKING_BUDGET_PRESETS,
    TEACHING_MAP_THINKING_BUDGET_DEFAULT,
    (os.getenv("TEACHING_MAP_THINKING_BUDGET_DEFAULT_PRESET", "") or "").strip(),
)
TEACHING_MAP_DEFAULT_MODEL_ICON = os.getenv(
    "TEACHING_MAP_DEFAULT_MODEL_ICON",
    "images/model-icons/model-default.svg",
).strip().lstrip("/")
_DEFAULT_TEACHING_MAP_MODEL_ICON_MAP = {
    "Pro/MiniMaxAI/MiniMax-M2.5": "images/model-icons/minimax.svg",
    "Pro/zai-org/GLM-5": "images/model-icons/glm.svg",
    "Qwen/Qwen3.5-397B-A17B": "images/model-icons/qwen.svg",
    "Pro/deepseek-ai/DeepSeek-R1": "images/model-icons/deepseek.svg",
    "moonshotai/Kimi-K2-Thinking": "images/model-icons/kimi.svg",
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
LLM_GENERATOR_MODEL_NAME = TEACHING_MAP_GENERATOR_MODEL_NAME
LLM_VALIDATOR_MODEL_NAME = TEACHING_MAP_VALIDATOR_MODEL_NAME
LLM_SELECTABLE_MODEL_IDS = TEACHING_MAP_SELECTABLE_MODEL_IDS
LLM_THINKING_SUPPORTED_MODEL_IDS = TEACHING_MAP_THINKING_SUPPORTED_MODEL_IDS
LLM_THINKING_DEFAULT_ENABLED = TEACHING_MAP_THINKING_DEFAULT_ENABLED
LLM_THINKING_BUDGET_DEFAULT = TEACHING_MAP_THINKING_BUDGET_DEFAULT
LLM_THINKING_BUDGET_MIN = TEACHING_MAP_THINKING_BUDGET_MIN
LLM_THINKING_BUDGET_MAX = TEACHING_MAP_THINKING_BUDGET_MAX
LLM_THINKING_BUDGET_PRESETS = TEACHING_MAP_THINKING_BUDGET_PRESETS
LLM_THINKING_BUDGET_DEFAULT_PRESET = TEACHING_MAP_THINKING_BUDGET_DEFAULT_PRESET
LLM_DEFAULT_MODEL_ICON = TEACHING_MAP_DEFAULT_MODEL_ICON
LLM_MODEL_ICON_MAP = TEACHING_MAP_MODEL_ICON_MAP
LLM_IMAGE_PARSER_MODEL_NAME = TEACHING_MAP_IMAGE_PARSER_MODEL_NAME
MAX_VALIDATION_RETRIES = TEACHING_MAP_MAX_VALIDATION_RETRIES
