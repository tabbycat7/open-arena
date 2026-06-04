"""Image generation service for teaching map visual aids.

Supports:
- Gemini multimodal chat (/v1/chat/completions + modalities image)
- AiHubMix predictions API (/v1/models/.../predictions)
- OpenAI-compatible /v1/images/generations

Falls back gracefully on failure.
"""

import base64
import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from config import (
    IMAGE_GEN_API_KEY,
    IMAGE_GEN_API_MODE,
    IMAGE_GEN_ASPECT_RATIO,
    IMAGE_GEN_BASE_URL,
    IMAGE_GEN_MAX_WORKERS,
    IMAGE_GEN_MODEL,
    IMAGE_GEN_MODEL_PATH,
    IMAGE_GEN_QUALITY,
    IMAGE_GEN_SIZE,
    IMAGE_GEN_TIMEOUT,
)

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads" / "visual_aids"

# Models documented to work with POST .../images/generations on AiHubMix
_OPENAI_IMAGES_GENERATIONS_MODELS = frozenset({
    "dall-e-2",
    "dall-e-3",
    "gpt-image-1",
    "gpt-image-1-mini",
    "gpt-image-1.5",
    "gpt-image-2",
    "FLUX.1-Kontext-pro",
})

# doubao-seedream-5.x 等要求总像素 >= 1920*1920
_DOUBAO_MIN_PIXELS = 3686400

_GEMINI_CHAT_ASPECT_RATIOS = frozenset({
    "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9",
})


def _ensure_task_dir(task_id: str) -> Path:
    task_dir = UPLOAD_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


def _safe_filename(node_id: str) -> str:
    safe = node_id.replace("/", "_").replace("\\", "_").replace("..", "_")
    if not safe:
        safe = hashlib.md5(node_id.encode()).hexdigest()[:12]
    return safe


def generate_image_for_node(
    task_id: str,
    node_id: str,
    visual_aid_prompt: str,
    subject: str = "",
    grade: str = "",
) -> Optional[str]:
    """Generate a single image for a question node.

    Returns the relative URL path (under /static/) on success, or None on failure.
    """
    if not visual_aid_prompt or not visual_aid_prompt.strip():
        return None

    full_prompt = _build_image_prompt(visual_aid_prompt, subject, grade)

    try:
        image_ref = _call_image_api(full_prompt)
        if not image_ref:
            return None
        return _persist_image(image_ref, task_id, node_id)
    except Exception:
        logger.exception("Image generation failed for node %s in task %s", node_id, task_id)
        return None


def _collect_visual_aid_jobs(questions: List[dict]) -> List[Tuple[dict, str, str]]:
    jobs: List[Tuple[dict, str, str]] = []
    for node in questions or []:
        node_id = node.get("id", "")
        if not node_id:
            continue
        if node.get("visual_aid_type", "") == "none":
            continue
        prompt = node.get("visual_aid_prompt", "")
        if prompt and prompt.strip():
            jobs.append((node, node_id, prompt.strip()))
    return jobs


def _resolve_worker_count(job_count: int, max_workers: Optional[int] = None) -> int:
    if max_workers is None:
        max_workers = IMAGE_GEN_MAX_WORKERS
    try:
        worker_count = max(1, int(max_workers or 5))
    except (TypeError, ValueError):
        worker_count = 5
    if _is_gemini_multimodal_image_model():
        # Gemini 生图较慢，并发过高容易触发读超时
        worker_count = min(worker_count, 2)
    return min(worker_count, max(1, job_count))


def generate_images_for_questions(
    task_id: str,
    questions: List[dict],
    subject: str = "",
    grade: str = "",
    max_workers: Optional[int] = None,
) -> Dict[str, List[str]]:
    """Generate images for question dicts concurrently and write URLs back."""
    jobs = _collect_visual_aid_jobs(questions)
    results: Dict[str, List[str]] = {}
    failed = 0
    attempted = len(jobs)

    if not jobs:
        return results

    worker_count = _resolve_worker_count(len(jobs), max_workers=max_workers)

    if worker_count == 1:
        for node, node_id, prompt in jobs:
            url = generate_image_for_node(task_id, node_id, prompt, subject, grade)
            if url:
                node["visual_aid_urls"] = [url]
                results[node_id] = [url]
            else:
                failed += 1
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = {
                pool.submit(
                    generate_image_for_node,
                    task_id,
                    node_id,
                    prompt,
                    subject,
                    grade,
                ): (node, node_id)
                for node, node_id, prompt in jobs
            }
            for fut in as_completed(futures):
                node, node_id = futures[fut]
                try:
                    url = fut.result()
                except Exception:
                    logger.exception("Visual aid worker failed for node %s", node_id)
                    url = None
                if url:
                    node["visual_aid_urls"] = [url]
                    results[node_id] = [url]
                else:
                    failed += 1

    if attempted and failed == attempted:
        logger.warning(
            "All %d visual aid image requests failed (model=%s, mode=%s). "
            "Check TEACHING_MAP_IMAGE_GEN_MODEL / TEACHING_MAP_IMAGE_GEN_API_MODE in .env",
            attempted,
            IMAGE_GEN_MODEL,
            IMAGE_GEN_API_MODE,
        )

    return results


def generate_images_for_map(
    task_id: str,
    teaching_map: dict,
    subject: str = "",
    grade: str = "",
) -> Dict[str, List[str]]:
    """Generate images for all nodes that have a visual_aid_prompt."""
    return generate_images_for_questions(task_id, teaching_map.get("nodes", []), subject, grade)


def get_visual_aid_url(task_id: str, node_id: str) -> Optional[str]:
    """Check if a visual aid image exists for a given node and return its URL."""
    task_dir = UPLOAD_DIR / task_id
    safe_name = _safe_filename(node_id)

    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        file_path = task_dir / (safe_name + ext)
        if file_path.exists():
            return "/static/uploads/visual_aids/%s/%s%s" % (task_id, safe_name, ext)

    return None


def save_uploaded_image(task_id: str, node_id: str, file_data: bytes, extension: str = ".png") -> str:
    """Save a teacher-uploaded image for a node. Returns the relative URL path."""
    task_dir = _ensure_task_dir(task_id)
    safe_name = _safe_filename(node_id)

    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        old_file = task_dir / (safe_name + ext)
        if old_file.exists():
            old_file.unlink()

    if not extension.startswith("."):
        extension = "." + extension
    file_path = task_dir / (safe_name + extension)
    file_path.write_bytes(file_data)

    return "/static/uploads/visual_aids/%s/%s%s" % (task_id, safe_name, extension)


def delete_node_image(task_id: str, node_id: str) -> bool:
    """Delete all visual aid images for a node."""
    task_dir = UPLOAD_DIR / task_id
    safe_name = _safe_filename(node_id)
    deleted = False

    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        file_path = task_dir / (safe_name + ext)
        if file_path.exists():
            file_path.unlink()
            deleted = True

    return deleted


def _build_image_prompt(visual_aid_prompt: str, subject: str, grade: str) -> str:
    parts = [
        "Educational illustration for a %s %s classroom." % (grade, subject)
        if subject
        else "Educational classroom illustration.",
        "Style: clean, simple, suitable for students. White background, clear labels in Chinese.",
        "Content: %s" % visual_aid_prompt.strip(),
    ]
    return " ".join(parts)


def _parse_pixel_size(size_str: str) -> Optional[int]:
    """Parse WxH (e.g. 1024x1024) into total pixel count."""
    match = re.match(r"^(\d+)\s*[xX*]\s*(\d+)$", (size_str or "").strip())
    if not match:
        return None
    return int(match.group(1)) * int(match.group(2))


def _resolve_size_for_predictions(model_path: str) -> str:
    """Map TEACHING_MAP_IMAGE_GEN_SIZE to provider-specific valid values."""
    raw = (IMAGE_GEN_SIZE or "").strip()
    lower_path = model_path.lower()

    if "doubao" in lower_path:
        upper = raw.upper()
        if upper in ("2K", "4K", "AUTO"):
            return upper
        if upper == "1K":
            return "2K"

        pixels = _parse_pixel_size(raw)
        if pixels is not None:
            if pixels < _DOUBAO_MIN_PIXELS:
                logger.debug(
                    "Doubao image size %s (%d px) below minimum %d; using 2K",
                    raw,
                    pixels,
                    _DOUBAO_MIN_PIXELS,
                )
                return "2K"
            return raw

        return "2K"

    # openai/* predictions expects WIDTHxHEIGHT, not symbolic sizes like 2K/4K/auto
    if lower_path.startswith("openai/"):
        upper = raw.upper()
        if upper in ("1K", "AUTO", ""):
            return "1024x1024"
        if upper == "2K":
            return "1536x1024"
        if upper == "4K":
            return "2048x2048"
        pixels = _parse_pixel_size(raw)
        if pixels is not None:
            return raw
        logger.debug("OpenAI predictions size '%s' invalid; fallback to 1024x1024", raw)
        return "1024x1024"

    return raw or "1024x1024"


def _resolve_size_for_openai_images() -> str:
    """Map symbolic sizes to WIDTHxHEIGHT for /images/generations."""
    raw = (IMAGE_GEN_SIZE or "").strip()
    upper = raw.upper()
    if upper in ("", "AUTO", "1K"):
        return "1024x1024"
    if upper == "2K":
        return "1536x1024"
    if upper == "4K":
        return "2048x2048"
    if _parse_pixel_size(raw) is not None:
        return raw
    return "1024x1024"


def _map_quality_for_predictions(quality: str) -> str:
    q = (quality or "").strip().lower()
    if q in ("low", "medium", "high"):
        return q
    if q in ("hd", "high"):
        return "high"
    if q in ("standard", "auto"):
        return "medium"
    return "medium"


def _is_gemini_multimodal_image_model() -> bool:
    """Models like gemini-3.1-flash-image-preview use chat/completions, not predictions."""
    name = (IMAGE_GEN_MODEL or "").lower()
    if "gemini" not in name:
        return False
    return "image" in name or "flash-image" in name


def _resolve_gemini_aspect_ratio() -> str:
    explicit = (IMAGE_GEN_ASPECT_RATIO or "").strip()
    if explicit in _GEMINI_CHAT_ASPECT_RATIOS:
        return explicit

    raw = (IMAGE_GEN_SIZE or "").strip().upper()
    if raw in ("1K", "AUTO", ""):
        return "1:1"
    if raw == "2K":
        return "4:3"
    if raw == "4K":
        return "16:9"

    match = re.match(r"^(\d+)\s*[xX*]\s*(\d+)$", (IMAGE_GEN_SIZE or "").strip())
    if match:
        w, h = int(match.group(1)), int(match.group(2))
        if w == h:
            return "1:1"
        if w > h:
            return "16:9" if w / max(h, 1) >= 1.6 else "4:3"
        return "2:3" if h / max(w, 1) >= 1.5 else "3:4"

    return "4:3"


def _resolve_model_path() -> str:
    if IMAGE_GEN_MODEL_PATH:
        return IMAGE_GEN_MODEL_PATH.strip("/")

    model = IMAGE_GEN_MODEL.strip()
    if "/" in model:
        return model

    lower = model.lower()
    if lower.startswith("doubao"):
        return "doubao/%s" % model
    if lower.startswith("qwen"):
        return "qianfan/%s" % model
    if lower.startswith("gemini"):
        return "google/%s" % model
    if lower.startswith("imagen"):
        return "google/%s" % model
    if lower.startswith("ernie-irag") or lower.startswith("irag"):
        return "qianfan/%s" % model
    if lower.startswith("flux") or model.startswith("FLUX"):
        return "bfl/%s" % model
    if lower.startswith("ideogram"):
        return "ideogram/%s" % model

    return "openai/%s" % model


def _should_use_predictions_first() -> bool:
    mode = (IMAGE_GEN_API_MODE or "auto").lower()
    if mode in ("gemini", "chat"):
        return False
    if mode == "predictions":
        return True
    if mode == "openai":
        return False
    if _is_gemini_multimodal_image_model():
        return False
    # auto: non-OpenAI generations models use predictions API
    return IMAGE_GEN_MODEL not in _OPENAI_IMAGES_GENERATIONS_MODELS


def _call_image_api(prompt: str) -> Optional[str]:
    if not IMAGE_GEN_API_KEY:
        logger.warning("No API key configured for image generation")
        return None

    mode = (IMAGE_GEN_API_MODE or "auto").lower()
    if _is_gemini_multimodal_image_model() and mode in ("auto", "gemini", "chat"):
        ref = _call_gemini_chat_image_api(prompt)
        if ref:
            return ref
        # Gemini 图像模型只支持 chat/completions，禁止回退到 images/predictions
        return None

    if _should_use_predictions_first():
        ref = _call_predictions_api(prompt)
        if ref:
            return ref
        if (IMAGE_GEN_API_MODE or "").lower() == "predictions":
            return None
        if IMAGE_GEN_MODEL in _OPENAI_IMAGES_GENERATIONS_MODELS:
            return _call_openai_images_api(prompt, log_404_as_warning=False)
        return None

    ref = _call_openai_images_api(prompt, log_404_as_warning=True)
    if ref:
        return ref
    return _call_predictions_api(prompt)


def _call_gemini_chat_image_api(prompt: str) -> Optional[str]:
    """AiHubMix Gemini image via chat/completions + modalities (see platform docs)."""
    base = IMAGE_GEN_BASE_URL.rstrip("/")
    url = "%s/chat/completions" % base
    aspect_ratio = _resolve_gemini_aspect_ratio()
    headers = {
        "Authorization": "Bearer %s" % IMAGE_GEN_API_KEY,
        "Content-Type": "application/json",
    }
    body = {
        "model": IMAGE_GEN_MODEL,
        "messages": [
            {"role": "system", "content": "aspect_ratio=%s" % aspect_ratio},
            {"role": "user", "content": [{"type": "text", "text": prompt}]},
        ],
        "modalities": ["text", "image"],
    }

    timeout = max(30, int(IMAGE_GEN_TIMEOUT or 300))
    last_err = None
    for attempt in range(2):
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            ref = _extract_gemini_chat_image_ref(data)
            if ref:
                return ref
            logger.warning(
                "Gemini chat image returned no inline_data for model %s: %s",
                IMAGE_GEN_MODEL,
                _json_preview(data),
            )
            return None
        except requests.HTTPError as exc:
            logger.warning(
                "Gemini chat image API error (%s): %s",
                exc.response.status_code if exc.response is not None else "?",
                _response_error_preview(exc.response),
            )
            return None
        except (requests.exceptions.Timeout, requests.exceptions.ReadTimeout) as exc:
            last_err = exc
            if attempt == 0:
                logger.warning(
                    "Gemini chat image timed out (%ss), retrying once...",
                    timeout,
                )
                continue
            logger.warning(
                "Gemini chat image timed out after retry (%ss). "
                "Increase TEACHING_MAP_IMAGE_GEN_TIMEOUT or lower MAX_WORKERS.",
                timeout,
            )
            return None
        except requests.RequestException as exc:
            last_err = exc
            break

    if last_err:
        logger.warning("Gemini chat image API request failed: %s", last_err)
    return None


def _extract_gemini_chat_image_ref(data: dict) -> Optional[str]:
    """Parse multi_mod_content / inline_data from chat completion response."""
    choices = data.get("choices") or []
    if not choices:
        return None

    message = choices[0].get("message") or {}
    parts = message.get("multi_mod_content")
    if isinstance(parts, list):
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline = part.get("inline_data")
            if isinstance(inline, dict):
                b64 = inline.get("data")
                if isinstance(b64, str) and b64.strip():
                    return b64.strip()

    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            inline = block.get("inline_data")
            if isinstance(inline, dict) and inline.get("data"):
                return str(inline["data"]).strip()
            if block.get("type") == "image_url":
                url_obj = block.get("image_url") or {}
                url = url_obj.get("url", "") if isinstance(url_obj, dict) else str(url_obj)
                if url.startswith("data:image") and "," in url:
                    return url.split(",", 1)[1]

    return _deep_find_inline_data(data)


def _deep_find_inline_data(obj: Any, depth: int = 0) -> Optional[str]:
    if depth > 10:
        return None
    if isinstance(obj, dict):
        if "inline_data" in obj and isinstance(obj["inline_data"], dict):
            data = obj["inline_data"].get("data")
            if isinstance(data, str) and len(data) > 100:
                return data.strip()
        for val in obj.values():
            found = _deep_find_inline_data(val, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _deep_find_inline_data(item, depth + 1)
            if found:
                return found
    return None


def _call_openai_images_api(prompt: str, log_404_as_warning: bool = True) -> Optional[str]:
    base = IMAGE_GEN_BASE_URL.rstrip("/")
    url = "%s/images/generations" % base
    headers = {
        "Authorization": "Bearer %s" % IMAGE_GEN_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "model": IMAGE_GEN_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": _resolve_size_for_openai_images(),
        "quality": IMAGE_GEN_QUALITY,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        if resp.status_code == 404 and log_404_as_warning:
            logger.warning(
                "Image API 404 at %s — try TEACHING_MAP_IMAGE_GEN_API_MODE=predictions "
                "or a model path like doubao/doubao-seedream-4-0",
                url,
            )
            return None
        resp.raise_for_status()
        return _extract_image_ref(resp.json())
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status == 404 and log_404_as_warning:
            logger.warning("Image generations endpoint not available: %s", url)
            return None
        logger.warning(
            "OpenAI images API error (%s): %s",
            status,
            _response_error_preview(exc.response),
        )
        return None
    except requests.RequestException:
        logger.warning("OpenAI images API request failed", exc_info=True)
        return None


def _call_predictions_api(prompt: str) -> Optional[str]:
    model_path = _resolve_model_path()
    base = IMAGE_GEN_BASE_URL.rstrip("/")
    url = "%s/models/%s/predictions" % (base, model_path)
    headers = {
        "Authorization": "Bearer %s" % IMAGE_GEN_API_KEY,
        "Content-Type": "application/json",
    }

    resolved_size = _resolve_size_for_predictions(model_path)
    input_payload: Dict[str, Any] = {
        "prompt": prompt,
        "size": resolved_size,
        "n": 1,
        "quality": _map_quality_for_predictions(IMAGE_GEN_QUALITY),
    }

    if model_path.startswith("google/"):
        # Google image endpoints commonly use numberOfImages instead of n.
        # Keep prompt as core field and provide numberOfImages for compatibility.
        input_payload.pop("n", None)
        input_payload["numberOfImages"] = 1

    if model_path.startswith("doubao/"):
        # doubao-seedream-5.x 在 predictions 接口下不接受 response_format 参数
        # （会返回 400: The parameter `response_format` is not valid）
        # 仅保留通用字段，避免参数校验失败。
        input_payload["watermark"] = False
        input_payload["stream"] = False

    body = {"input": input_payload}

    try:
        resp = requests.post(url, json=body, headers=headers, timeout=180)
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, dict) and data.get("output"):
            first = data["output"][0] if isinstance(data["output"], list) and data["output"] else None
            if isinstance(first, dict) and first.get("polling_url"):
                logger.warning(
                    "Image model %s returned async task; polling not implemented. "
                    "Use a synchronous model or gpt-image-1 via openai mode.",
                    IMAGE_GEN_MODEL,
                )
                return None

        ref = _extract_image_ref(data)
        if ref:
            return ref
        logger.warning(
            "Predictions API returned no image for model %s (path=%s): %s",
            IMAGE_GEN_MODEL,
            model_path,
            _json_preview(data),
        )
        return None
    except requests.HTTPError as exc:
        err_text = _response_error_preview(exc.response)
        if "prompt_not_found" in err_text:
            logger.warning(
                "Predictions API reports prompt_not_found for %s. "
                "Likely model/endpoint mismatch. Consider using gpt-image-1 "
                "or a dedicated image model in .env.",
                model_path,
            )
        logger.warning(
            "Predictions API error for %s (%s): %s",
            model_path,
            exc.response.status_code if exc.response is not None else "?",
            err_text,
        )
        return None
    except requests.RequestException:
        logger.warning("Predictions API request failed for %s", model_path, exc_info=True)
        return None


def _extract_image_ref(data: Any) -> Optional[str]:
    """Extract URL or base64 string from various provider response shapes."""
    if not isinstance(data, dict):
        return None

    for item in data.get("data") or []:
        ref = _ref_from_item(item)
        if ref:
            return ref

    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            ref = _ref_from_item(item)
            if ref:
                return ref
    elif isinstance(output, dict):
        ref = _ref_from_item(output)
        if ref:
            return ref

    for key in ("url", "image_url"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    # Some providers return b64_json as list/dict, e.g. {"b64_json":[{"bytesBase64":"..."}]}
    b64_val = data.get("b64_json")
    ref = _ref_from_item(b64_val)
    if ref:
        return ref

    images = data.get("images")
    if isinstance(images, list):
        for item in images:
            ref = _ref_from_item(item)
            if ref:
                return ref

    return _deep_find_image_ref(data)


def _ref_from_item(item: Any) -> Optional[str]:
    if isinstance(item, str) and item.strip():
        s = item.strip()
        if s.startswith("http"):
            return s
        if len(s) > 200 and not s.startswith("{"):
            return s
    if isinstance(item, list):
        for elem in item:
            ref = _ref_from_item(elem)
            if ref:
                return ref
        return None
    if not isinstance(item, dict):
        return None
    for key in ("b64_json", "base64", "image_base64", "bytesBase64", "data"):
        val = item.get(key)
        if isinstance(val, str) and val.strip() and not val.strip().startswith("http"):
            if key == "data" and len(val.strip()) < 100:
                continue
            return val.strip()
    for key in ("url", "image_url"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    nested = item.get("image") or item.get("result")
    if isinstance(nested, dict):
        return _ref_from_item(nested)
    if isinstance(nested, str) and nested.strip():
        return nested.strip()
    return None


def _deep_find_image_ref(obj: Any, depth: int = 0, prefer_url: bool = False) -> Optional[str]:
    if depth > 8:
        return None

    b64_keys = ("b64_json", "base64", "image_base64")
    url_keys = ("url", "image_url")
    key_order = url_keys + b64_keys if prefer_url else b64_keys + url_keys

    if isinstance(obj, dict):
        for key in key_order:
            val = obj.get(key)
            if isinstance(val, str) and not val.strip():
                continue
            if key in b64_keys and isinstance(val, str) and len(val) > 100:
                return val.strip()
            if key in url_keys and isinstance(val, str) and val.startswith("http"):
                return val.strip()
        for val in obj.values():
            found = _deep_find_image_ref(val, depth + 1, prefer_url=prefer_url)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _deep_find_image_ref(item, depth + 1, prefer_url=prefer_url)
            if found:
                return found
    return None


_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PaideiaHub/1.0)",
    "Accept": "image/*,*/*",
}


def _download_image_bytes(url: str) -> Optional[bytes]:
    """Download image from CDN URL; may fail on SSL with some volces TOS links."""
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.get(
                url,
                headers=_DOWNLOAD_HEADERS,
                timeout=90,
            )
            resp.raise_for_status()
            if resp.content:
                return resp.content
        except requests.exceptions.SSLError as exc:
            last_err = exc
        except requests.RequestException as exc:
            last_err = exc
    if last_err:
        logger.warning(
            "Failed to download image from CDN (%s). "
            "Doubao models should use base64_json; check network/proxy. Error: %s",
            url.split("?")[0][:80],
            last_err,
        )
    return None


def _persist_image(image_ref: str, task_id: str, node_id: str) -> Optional[str]:
    task_dir = _ensure_task_dir(task_id)
    safe_name = _safe_filename(node_id)
    file_path = task_dir / (safe_name + ".png")

    if image_ref.startswith("http://") or image_ref.startswith("https://"):
        content = _download_image_bytes(image_ref)
        if not content:
            return None
        file_path.write_bytes(content)
        return "/static/uploads/visual_aids/%s/%s.png" % (task_id, safe_name)

    try:
        raw = image_ref
        if raw.startswith("data:image"):
            raw = raw.split(",", 1)[-1]
        file_path.write_bytes(base64.b64decode(raw))
        return "/static/uploads/visual_aids/%s/%s.png" % (task_id, safe_name)
    except Exception:
        logger.warning("Failed to decode base64 image", exc_info=True)
        return None


def _response_error_preview(response: Optional[requests.Response]) -> str:
    if response is None:
        return "no response"
    try:
        body = response.json()
        if isinstance(body, dict):
            err = body.get("error")
            if isinstance(err, dict):
                return str(err.get("message") or err)
            return str(body.get("message") or body)[:500]
    except Exception:
        pass
    return (response.text or "")[:500]


def _json_preview(data: Any) -> str:
    import json

    try:
        text = json.dumps(data, ensure_ascii=False)
    except Exception:
        text = str(data)
    return text[:400] + ("..." if len(text) > 400 else "")
