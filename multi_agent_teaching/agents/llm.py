"""LLM client initialization — OpenAI-compatible interface."""

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, Optional

from langchain_openai import ChatOpenAI
from agents.fake_api import FakeChatOpenAI
from config import (
    LLM_BASE_URL,
    LLM_API_KEY,
    LLM_MODEL_NAME,
    LLM_GENERATOR_MODEL_NAME,
    LLM_VALIDATOR_MODEL_NAME,
    LLM_IMAGE_PARSER_MODEL_NAME,
    LLM_THINKING_SUPPORTED_MODEL_IDS,
    LLM_THINKING_DEFAULT_ENABLED,
    LLM_THINKING_BUDGET_DEFAULT,
    LLM_THINKING_BUDGET_MIN,
    LLM_THINKING_BUDGET_MAX,
)


_GENERATOR_MODEL_OVERRIDE: ContextVar[Optional[str]] = ContextVar(
    "teaching_map_generator_model_override",
    default=None,
)
_GENERATOR_THINKING_OVERRIDE: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "teaching_map_generator_thinking_override",
    default=None,
)


def _use_fake_api() -> bool:
    return os.getenv("TEACHING_MAP_FAKE_API", "").strip().lower() in {"1", "true", "yes", "on"}


def _build_llm(model_name: str, temperature: float, model_kwargs: Optional[Dict[str, Any]] = None) -> ChatOpenAI:
    normalized_model_kwargs = dict(model_kwargs or {})
    extra_body = normalized_model_kwargs.pop("extra_body", None)

    if _use_fake_api():
        return FakeChatOpenAI(
            model=model_name,
            temperature=temperature,
            model_kwargs=normalized_model_kwargs,
            extra_body=extra_body,
        )

    kwargs: Dict[str, Any] = {
        "base_url": LLM_BASE_URL,
        "api_key": LLM_API_KEY,
        "model": model_name,
        "temperature": temperature,
        "model_kwargs": normalized_model_kwargs,
    }
    if extra_body is not None:
        kwargs["extra_body"] = extra_body

    return ChatOpenAI(
        **kwargs,
    )


def _resolve_generator_model_name(model_name: Optional[str] = None) -> str:
    if model_name:
        return model_name
    override = _GENERATOR_MODEL_OVERRIDE.get()
    if override:
        return override
    return LLM_GENERATOR_MODEL_NAME or LLM_MODEL_NAME


def _supports_thinking(model_name: str) -> bool:
    supported = {
        (item or "").strip()
        for item in (LLM_THINKING_SUPPORTED_MODEL_IDS or [])
        if isinstance(item, str)
    }
    return model_name in supported


def _normalize_thinking_budget(raw_budget: Optional[Any]) -> int:
    try:
        budget = int(raw_budget)
    except (TypeError, ValueError):
        budget = int(LLM_THINKING_BUDGET_DEFAULT)

    min_budget = int(LLM_THINKING_BUDGET_MIN)
    max_budget = int(LLM_THINKING_BUDGET_MAX)
    if budget < min_budget:
        return min_budget
    if budget > max_budget:
        return max_budget
    return budget


def _resolve_generator_model_kwargs(
    model_name: str,
    enable_thinking: Optional[bool] = None,
    thinking_budget: Optional[int] = None,
) -> Dict[str, Any]:
    if not _supports_thinking(model_name):
        return {}

    override = _GENERATOR_THINKING_OVERRIDE.get() or {}
    enabled = enable_thinking
    if enabled is None and isinstance(override, dict) and "enable_thinking" in override:
        enabled = bool(override.get("enable_thinking"))
    if enabled is None:
        enabled = bool(LLM_THINKING_DEFAULT_ENABLED)

    if not enabled:
        return {
            "extra_body": {
                "enable_thinking": False,
            }
        }

    budget_raw: Any = thinking_budget
    if budget_raw is None and isinstance(override, dict):
        budget_raw = override.get("thinking_budget")
    budget = _normalize_thinking_budget(budget_raw)
    return {
        "extra_body": {
            "enable_thinking": True,
            "thinking_budget": budget,
        }
    }


def get_generator_llm(
    temperature: float = 0.7,
    model_name: Optional[str] = None,
    enable_thinking: Optional[bool] = None,
    thinking_budget: Optional[int] = None,
) -> ChatOpenAI:
    resolved_model = _resolve_generator_model_name(model_name)
    model_kwargs = _resolve_generator_model_kwargs(
        resolved_model,
        enable_thinking=enable_thinking,
        thinking_budget=thinking_budget,
    )
    return _build_llm(resolved_model, temperature, model_kwargs=model_kwargs)


def get_validator_llm(temperature: float = 0.1) -> ChatOpenAI:
    return _build_llm(LLM_VALIDATOR_MODEL_NAME, temperature)


def get_image_parser_llm(temperature: float = 0) -> ChatOpenAI:
    return _build_llm(LLM_IMAGE_PARSER_MODEL_NAME, temperature)


@contextmanager
def use_generator_model(
    model_name: Optional[str],
    thinking_options: Optional[Dict[str, Any]] = None,
) -> Iterator[None]:
    token = _GENERATOR_MODEL_OVERRIDE.set(model_name or None)
    thinking_token = _GENERATOR_THINKING_OVERRIDE.set(thinking_options or None)
    try:
        yield
    finally:
        _GENERATOR_THINKING_OVERRIDE.reset(thinking_token)
        _GENERATOR_MODEL_OVERRIDE.reset(token)


def get_llm(temperature: float = 0.7) -> ChatOpenAI:
    """Backward compatibility: default to generator model."""
    model_name = LLM_GENERATOR_MODEL_NAME or LLM_MODEL_NAME
    return get_generator_llm(temperature=temperature, model_name=model_name)
