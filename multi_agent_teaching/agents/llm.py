"""LLM client initialization — OpenAI-compatible interface."""

from langchain_openai import ChatOpenAI
from config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL_NAME


def get_llm(temperature: float = 0.7) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=LLM_BASE_URL,
        api_key=LLM_API_KEY,
        model=LLM_MODEL_NAME,
        temperature=temperature,
    )
