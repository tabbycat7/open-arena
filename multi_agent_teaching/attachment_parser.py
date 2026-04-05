"""Attachment parsing utilities for teaching-map workflow.

This module converts uploaded files into plain text so the existing
workflow can inject them into prompts via the `attachment` field.
"""

from __future__ import annotations

import base64
import importlib
import io
import os
from typing import Optional

from langchain_core.messages import HumanMessage

from agents.llm import get_image_parser_llm


MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
MAX_EXTRACTED_CHARS = 12000

TEXT_EXTENSIONS = {"txt", "md", "markdown", "csv", "json"}
PDF_EXTENSIONS = {"pdf"}
DOCX_EXTENSIONS = {"docx"}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "bmp"}


def parse_uploaded_attachment(file_storage) -> str:
    """Parse uploaded file into prompt-friendly text.

    Returns a normalized text block that can be directly passed to
    workflow state as `attachment`.
    """
    if not file_storage or not getattr(file_storage, "filename", ""):
        return ""

    file_name = file_storage.filename or ""
    ext = _get_extension(file_name)
    mime_type = (getattr(file_storage, "mimetype", "") or "").strip().lower()

    raw = file_storage.read() or b""
    if not raw:
        return ""

    if len(raw) > MAX_ATTACHMENT_BYTES:
        return (
            "[附件解析]\n"
            f"文件名: {file_name}\n"
            f"状态: 附件过大（{len(raw)} bytes），已忽略。请压缩后重试。"
        )

    try:
        if ext in TEXT_EXTENSIONS:
            text = _decode_text(raw)
        elif ext in PDF_EXTENSIONS:
            text = _extract_pdf_text(raw)
        elif ext in DOCX_EXTENSIONS:
            text = _extract_docx_text(raw)
        elif ext in IMAGE_EXTENSIONS or mime_type.startswith("image/"):
            text = _extract_image_text_with_llm(raw, mime_type or _mime_from_ext(ext), file_name)
        else:
            text = (
                f"无法直接解析该文件类型（.{ext or 'unknown'}）。"
                "请上传 txt/md/pdf/docx 或图片。"
            )
    except Exception as exc:  # Keep upload path resilient.
        text = f"附件解析失败: {exc}"

    text = _trim(text)
    return (
        "[附件解析]\n"
        f"文件名: {file_name}\n"
        f"类型: {mime_type or 'unknown'}\n"
        "提取内容:\n"
        f"{text}"
    )


def _get_extension(file_name: str) -> str:
    _, ext = os.path.splitext(file_name)
    return ext.lower().lstrip(".")


def _trim(text: str) -> str:
    if not text:
        return ""
    if len(text) <= MAX_EXTRACTED_CHARS:
        return text
    return text[:MAX_EXTRACTED_CHARS] + "\n...（内容过长，已截断）"


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


def _extract_pdf_text(raw: bytes) -> str:
    try:
        PdfReader = importlib.import_module("pypdf").PdfReader
    except Exception:
        return "当前环境未安装 pypdf，无法提取 PDF 文本。"

    reader = PdfReader(io.BytesIO(raw))
    parts = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            parts.append(page_text.strip())
    return "\n\n".join(parts) if parts else "PDF 未提取到可读文本（可能是扫描件）。"


def _extract_docx_text(raw: bytes) -> str:
    try:
        Document = importlib.import_module("docx").Document
    except Exception:
        return "当前环境未安装 python-docx，无法提取 DOCX 文本。"

    doc = Document(io.BytesIO(raw))
    lines = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    return "\n".join(lines) if lines else "DOCX 未提取到可读文本。"


def _mime_from_ext(ext: str) -> str:
    if ext in {"jpg", "jpeg"}:
        return "image/jpeg"
    if ext == "png":
        return "image/png"
    if ext == "webp":
        return "image/webp"
    if ext == "bmp":
        return "image/bmp"
    return "image/jpeg"


def _normalize_llm_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                value = item.get("text") or item.get("content") or ""
                if value:
                    chunks.append(str(value))
        return "\n".join(chunks)
    return str(content)


def _extract_image_text_with_llm(raw: bytes, mime_type: str, file_name: str) -> str:
    """Use multimodal LLM to transcribe textbook photos into text."""
    data_uri = f"data:{mime_type};base64," + base64.b64encode(raw).decode("ascii")

    prompt = (
        "请提取这张教材/讲义图片中的可见文字与关键结构\n"
        "如果图片模糊，请明确标注不确定部分。"
    )

    try:
        llm = get_image_parser_llm(temperature=0)
        msg = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ]
        )
        resp = llm.invoke([msg])
        text = _normalize_llm_content(getattr(resp, "content", ""))
        if text.strip():
            return text
        return f"图片 {file_name} 已上传，但视觉模型未返回有效文本。"
    except Exception as exc:
        return f"图片 {file_name} 解析失败（视觉模型调用异常）: {exc}"
