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
    LLM_MAX_TOKENS,
    LLM_TIMEOUT,
    LLM_GENERATOR_MODEL_NAME,
    LLM_VALIDATOR_MODEL_NAME,
    LLM_IMAGE_PARSER_MODEL_NAME,
)


_GENERATOR_MODEL_OVERRIDE: ContextVar[Optional[str]] = ContextVar(
    "teaching_map_generator_model_override",
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
        "max_tokens": int(LLM_MAX_TOKENS),
        "timeout": int(LLM_TIMEOUT),
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


def get_state_temperature(state: Optional[Dict[str, Any]], default: float = 0.7) -> float:
    raw_value = default
    if isinstance(state, dict):
        candidate = state.get("temperature")
        if candidate not in (None, ""):
            raw_value = candidate
    try:
        parsed = float(raw_value)
    except (TypeError, ValueError):
        parsed = float(default)
    if parsed < 0:
        return 0.0
    if parsed > 2:
        return 2.0
    return parsed


def get_generator_llm(
    temperature: float = 0.7,
    model_name: Optional[str] = None,
) -> ChatOpenAI:
    resolved_model = _resolve_generator_model_name(model_name)
    return _build_llm(resolved_model, temperature)


def get_validator_llm(temperature: float = 0.1) -> ChatOpenAI:
    return _build_llm(LLM_VALIDATOR_MODEL_NAME, temperature)


def get_image_parser_llm(temperature: float = 0) -> ChatOpenAI:
    return _build_llm(LLM_IMAGE_PARSER_MODEL_NAME, temperature)


@contextmanager
def use_generator_model(
    model_name: Optional[str],
) -> Iterator[None]:
    token = _GENERATOR_MODEL_OVERRIDE.set(model_name or None)
    try:
        yield
    finally:
        _GENERATOR_MODEL_OVERRIDE.reset(token)


def get_llm(temperature: float = 0.7) -> ChatOpenAI:
    """Backward compatibility: default to generator model."""
    model_name = LLM_GENERATOR_MODEL_NAME or LLM_MODEL_NAME
    return get_generator_llm(temperature=temperature, model_name=model_name)
