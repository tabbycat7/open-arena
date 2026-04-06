"""Attachment parsing utilities for teaching-map workflow.

This module converts uploaded files into plain text so the existing
workflow can inject them into prompts via the `attachment` field.
"""

from __future__ import annotations

import base64
import importlib
import io
import json
import os
import re
from typing import List, Optional, Tuple

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
    parsed_text, _stats = parse_uploaded_attachments([file_storage])
    return parsed_text


def parse_uploaded_attachments(file_storages) -> Tuple[str, dict]:
    """Parse multiple attachments; image files are sent in a single LLM request."""
    blocks: List[str] = []
    stats = {"received": 0, "parsed": 0, "failed": 0}
    image_jobs = []

    for file_storage in file_storages or []:
        if not file_storage or not getattr(file_storage, "filename", ""):
            continue

        file_name = file_storage.filename or ""
        ext = _get_extension(file_name)
        mime_type = (getattr(file_storage, "mimetype", "") or "").strip().lower()
        stats["received"] += 1

        raw = file_storage.read() or b""
        if not raw:
            stats["failed"] += 1
            continue

        if len(raw) > MAX_ATTACHMENT_BYTES:
            text = f"状态: 附件过大（{len(raw)} bytes），已忽略。请压缩后重试。"
            blocks.append(_format_attachment_block(file_name, mime_type or "unknown", text))
            stats["failed"] += 1
            continue

        if ext in IMAGE_EXTENSIONS or mime_type.startswith("image/"):
            image_jobs.append(
                {
                    "file_name": file_name,
                    "mime_type": mime_type or _mime_from_ext(ext),
                    "raw": raw,
                    "block_index": len(blocks),
                }
            )
            blocks.append("")
            continue

        try:
            text = _extract_non_image_text(ext, raw)
        except Exception as exc:
            text = f"附件解析失败: {exc}"

        text = _trim(text)
        blocks.append(_format_attachment_block(file_name, mime_type or "unknown", text))
        if _is_failure_text(text):
            stats["failed"] += 1
        else:
            stats["parsed"] += 1

    if image_jobs:
        image_texts = _extract_images_text_with_llm_batch(image_jobs)
        for idx, job in enumerate(image_jobs):
            text = image_texts[idx] if idx < len(image_texts) else "图片已上传，但批量解析结果缺失。"
            text = _trim(text)
            blocks[job["block_index"]] = _format_attachment_block(job["file_name"], job["mime_type"], text)
            if _is_failure_text(text):
                stats["failed"] += 1
            else:
                stats["parsed"] += 1

    merged = "\n\n".join(part for part in blocks if part)
    return merged, stats


def _get_extension(file_name: str) -> str:
    _, ext = os.path.splitext(file_name)
    return ext.lower().lstrip(".")


def _format_attachment_block(file_name: str, mime_type: str, text: str) -> str:
    return (
        "[附件解析]\n"
        f"文件名: {file_name}\n"
        f"类型: {mime_type or 'unknown'}\n"
        "提取内容:\n"
        f"{text}"
    )


def _is_failure_text(text: str) -> bool:
    if not text:
        return True
    failure_markers = (
        "附件解析失败",
        "状态: 附件过大",
        "无法直接解析该文件类型",
        "解析失败",
    )
    return any(marker in text for marker in failure_markers)


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


def _extract_non_image_text(ext: str, raw: bytes) -> str:
    if ext in TEXT_EXTENSIONS:
        return _decode_text(raw)
    if ext in PDF_EXTENSIONS:
        return _extract_pdf_text(raw)
    if ext in DOCX_EXTENSIONS:
        return _extract_docx_text(raw)
    return (
        f"无法直接解析该文件类型（.{ext or 'unknown'}）。"
        "请上传 txt/md/pdf/docx 或图片。"
    )


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
    """Use multimodal LLM to transcribe one image."""
    items = [{"file_name": file_name, "mime_type": mime_type, "raw": raw}]
    results = _extract_images_text_with_llm_batch(items)
    if results:
        return results[0]
    return f"图片 {file_name} 已上传，但视觉模型未返回有效文本。"


def _extract_images_text_with_llm_batch(image_items: List[dict]) -> List[str]:
    prompt = (
        "你将收到多张教材/讲义图片。请逐张提取可见文字和关键结构，保持原有层级、公式与列表。\n"
        "必须只返回 JSON，不要 Markdown，不要额外解释。\n"
        '输出格式: {"items":[{"index":1,"text":"..."}]}\n'
        "index 从 1 开始，且必须覆盖每一张图片。若有模糊区域，请在对应 text 中标注不确定部分。"
    )

    content = [{"type": "text", "text": prompt}]
    for idx, item in enumerate(image_items, start=1):
        file_name = str(item.get("file_name", ""))
        mime_type = str(item.get("mime_type", "") or "image/jpeg")
        raw = item.get("raw") or b""
        data_uri = f"data:{mime_type};base64," + base64.b64encode(raw).decode("ascii")
        content.append({"type": "text", "text": f"图片 {idx}: {file_name}"})
        content.append({"type": "image_url", "image_url": {"url": data_uri}})

    try:
        llm = get_image_parser_llm(temperature=0)
        msg = HumanMessage(content=content)
        resp = llm.invoke([msg])
        raw_text = _normalize_llm_content(getattr(resp, "content", ""))
        parsed = _parse_batch_image_json(raw_text, len(image_items))
        if parsed is not None:
            return parsed
        return _fallback_batch_image_texts(raw_text, len(image_items))
    except Exception as exc:
        return [
            f"图片 {item.get('file_name', '')} 解析失败（视觉模型批量调用异常）: {exc}"
            for item in image_items
        ]


def _parse_batch_image_json(raw_text: str, expected_count: int) -> Optional[List[str]]:
    payload = _extract_json_payload(raw_text)
    if not isinstance(payload, dict):
        return None
    items = payload.get("items")
    if not isinstance(items, list):
        return None

    outputs = [""] * expected_count
    filled = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index")) - 1
        except Exception:
            continue
        if index < 0 or index >= expected_count:
            continue
        text = str(item.get("text", "")).strip()
        if text:
            outputs[index] = text
            filled += 1

    if filled == 0:
        return None

    for i, text in enumerate(outputs):
        if not text:
            outputs[i] = "该图片包含在批量解析中，但模型未返回独立内容。"
    return outputs


def _extract_json_payload(raw_text: str):
    text = (raw_text or "").strip()
    if not text:
        return None

    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def _fallback_batch_image_texts(raw_text: str, expected_count: int) -> List[str]:
    text = (raw_text or "").strip()
    if expected_count <= 0:
        return []
    if expected_count == 1:
        return [text or "图片已上传，但视觉模型未返回有效文本。"]
    if not text:
        return ["图片已上传，但视觉模型未返回有效文本。" for _ in range(expected_count)]

    # Keep one combined copy to avoid exploding prompt length for large batches.
    results = [text]
    for _ in range(expected_count - 1):
        results.append("该图片已包含在同一次批量解析请求中，请参考第一条合并解析结果。")
    return results
