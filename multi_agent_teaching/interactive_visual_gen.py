"""Interactive HTML visual generation service for teaching map nodes.

The generated code is rendered only inside sandboxed iframes on the frontend.
This module still validates the HTML because a sandbox is a safety layer, not
an invitation to ship arbitrary network-capable documents.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import INTERACTIVE_VISUAL_MAX_WORKERS, INTERACTIVE_VISUAL_MODEL_NAME


logger = logging.getLogger(__name__)

_BANNED_TAGS = {"base", "embed", "form", "iframe", "link", "object"}
_URL_ATTRS = {"action", "href", "poster", "src", "srcset"}
_BANNED_JS_PATTERNS = [
    r"\bfetch\s*\(",
    r"\bXMLHttpRequest\b",
    r"\bWebSocket\b",
    r"\bEventSource\b",
    r"\bsendBeacon\s*\(",
    r"\bimport\s*\(",
    r"\blocalStorage\b",
    r"\bsessionStorage\b",
    r"\bindexedDB\b",
    r"\bdocument\s*\.\s*cookie\b",
    r"\b(?:window\s*\.\s*)?parent\s*[.\[]",
    r"\b(?:window\s*\.\s*)?top\s*[.\[]",
    r"\bopener\s*[.\[]",
    r"\bpostMessage\s*\(",
    r"\blocation\s*\.\s*(?:href|assign|replace)\b",
    r"\bwindow\s*\.\s*location\b",
]


class UnsafeInteractiveVisualError(ValueError):
    """Raised when generated HTML violates the sandbox contract."""


class _SafetyHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.errors: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag_l = tag.lower()
        if tag_l in _BANNED_TAGS:
            self.errors.append("禁止使用 <%s> 标签" % tag_l)

        for raw_name, raw_value in attrs:
            name = (raw_name or "").lower()
            value = (raw_value or "").strip()
            value_l = value.lower()

            if name.startswith("on"):
                self.errors.append("禁止使用内联事件属性 %s" % name)
            if name in _URL_ATTRS and value:
                self._validate_url_attr(name, value_l)

    def _validate_url_attr(self, name: str, value_l: str) -> None:
        if name == "srcset":
            self.errors.append("禁止使用 srcset")
            return
        if value_l.startswith(("#", "data:image/")):
            return
        if re.match(r"^[a-z][a-z0-9+.-]*:", value_l) or value_l.startswith("//"):
            self.errors.append("禁止外部或协议型资源引用：%s" % name)


def _use_fake_api() -> bool:
    return os.getenv("TEACHING_MAP_FAKE_API", "").strip().lower() in {"1", "true", "yes", "on"}


def _get_generator_llm():
    try:
        from agents.llm import get_generator_llm
    except ImportError:  # pragma: no cover - used when imported as package module
        package_dir = str(Path(__file__).resolve().parent)
        if package_dir not in sys.path:
            sys.path.insert(0, package_dir)
        from agents.llm import get_generator_llm
    return get_generator_llm


def _safe_node_key(node_id: str) -> str:
    raw = node_id or "node"
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw).strip("_")
    return safe or hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _strip_code_fence(content: str) -> str:
    text = (content or "").strip()
    if "```" not in text:
        return text
    match = re.search(r"```(?:html|HTML)?\s*(.*?)```", text, re.S)
    return (match.group(1) if match else text.replace("```", "")).strip()


def _insert_csp(html: str) -> str:
    csp = (
        "<meta http-equiv=\"Content-Security-Policy\" content=\""
        "default-src 'none'; "
        "script-src 'unsafe-inline'; "
        "style-src 'unsafe-inline'; "
        "img-src data:; "
        "font-src 'none'; "
        "connect-src 'none'; "
        "base-uri 'none'; "
        "form-action 'none'; "
        "frame-src 'none'; "
        "media-src 'none'; "
        "object-src 'none'"
        "\">"
    )
    if re.search(r"<meta[^>]+http-equiv=[\"']Content-Security-Policy[\"']", html, re.I):
        return html
    if re.search(r"<head[^>]*>", html, re.I):
        return re.sub(r"(<head[^>]*>)", r"\1\n" + csp, html, count=1, flags=re.I)
    if re.search(r"<html[^>]*>", html, re.I):
        return re.sub(r"(<html[^>]*>)", r"\1\n<head>" + csp + "</head>", html, count=1, flags=re.I)
    return "<!doctype html><html><head>%s</head><body>%s</body></html>" % (csp, html)


def validate_interactive_visual_html(html: str) -> str:
    """Return CSP-wrapped HTML if safe, otherwise raise."""
    candidate = _strip_code_fence(html)
    if not candidate:
        raise UnsafeInteractiveVisualError("HTML 为空")
    if len(candidate.encode("utf-8")) > 180_000:
        raise UnsafeInteractiveVisualError("HTML 过大")
    if not re.search(r"<\s*(?:html|body|svg|canvas|div)\b", candidate, re.I):
        raise UnsafeInteractiveVisualError("未检测到可渲染的 HTML / SVG / Canvas 结构")

    parser = _SafetyHTMLParser()
    parser.feed(candidate)
    if parser.errors:
        raise UnsafeInteractiveVisualError("; ".join(parser.errors[:3]))

    for pattern in _BANNED_JS_PATTERNS:
        if re.search(pattern, candidate, re.I):
            raise UnsafeInteractiveVisualError("包含禁止的脚本能力：%s" % pattern)

    return _insert_csp(candidate)


def _build_visual_prompt(node: dict, subject: str, grade: str) -> str:
    return """你是一个课堂教学交互可视化工程师。请为下面的问题生成一个完整、自包含的 HTML 文档。

目标：
- 用 HTML + SVG / Canvas / CSS / 内联 JavaScript 做准确、可控、可交互的教学可视化。
- 可视化服务于题干，不要替学生直接给出完整答案。
- 适合课堂投屏：清爽、字号清晰、中文标签准确、默认 4:3 宽高自适应。

安全与技术约束：
- 只输出 HTML 代码，不要输出 Markdown 解释。
- 不要使用任何外部资源、外链脚本、远程图片、字体、iframe、表单、跳转或网络请求。
- 不要使用 srcset、script src、fetch、XMLHttpRequest、WebSocket、localStorage、sessionStorage、document.cookie、window.parent、window.top、postMessage。
- 不要写 onclick/oninput 等内联事件属性；如需交互，用脚本里的 addEventListener。
- 所有 CSS 和 JS 必须内联在同一个 HTML 文档中。

建议交互：
- 若适合，用滑块、按钮、拖动点、高亮切换或 Canvas 动画帮助学生观察变量关系。
- 若不适合复杂交互，生成准确的 SVG 示意图和少量高亮按钮即可。

课程信息：
- 学科：{subject}
- 年级：{grade}

问题节点：
- ID：{node_id}
- 题干：{content}
- 知识点：{knowledge_points}
- 认知层次：{cognitive_level}
- 难度：{difficulty}
- 设计意图：{design_intent}
- 可视化类型：{visual_aid_type}
- 可视化描述：{visual_aid_prompt}
""".format(
        subject=subject or "未指定",
        grade=grade or "未指定",
        node_id=node.get("id", ""),
        content=node.get("content", ""),
        knowledge_points="、".join(node.get("knowledge_points", []) or []),
        cognitive_level=node.get("cognitive_level", ""),
        difficulty=node.get("difficulty", ""),
        design_intent=node.get("design_intent") or node.get("design_rationale", ""),
        visual_aid_type=node.get("visual_aid_type", ""),
        visual_aid_prompt=node.get("visual_aid_prompt", ""),
    )


def _fallback_fake_html(node: dict) -> str:
    title = node.get("visual_aid_prompt") or node.get("content") or "交互可视化"
    node_key = _safe_node_key(node.get("id", "node"))
    html = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
html,body{margin:0;height:100%%;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#fff;color:#172033}
.wrap{box-sizing:border-box;min-height:100%%;display:grid;place-items:center;padding:28px}
.card{width:min(760px,100%%);border:1px solid #dbe4f0;border-radius:14px;padding:26px;background:#f8fbff}
h1{font-size:24px;margin:0 0 14px}.bar{height:16px;background:#dbeafe;border-radius:999px;overflow:hidden}.fill{height:100%%;width:45%%;background:#4f46e5;transition:width .25s}
button{margin-top:18px;border:0;border-radius:10px;background:#4f46e5;color:#fff;padding:10px 16px;font-size:15px}
</style>
</head>
<body>
<div class="wrap"><div class="card"><h1>%s</h1><p>拖动或点击观察关键量的变化。</p><div class="bar"><div class="fill" id="fill-%s"></div></div><button id="btn-%s">切换高亮</button></div></div>
<script>
(function(){var on=false;var fill=document.getElementById("fill-%s");document.getElementById("btn-%s").addEventListener("click",function(){on=!on;fill.style.width=on?"78%%":"45%%";});})();
</script>
</body>
</html>""" % (
        _html_escape(title),
        node_key,
        node_key,
        node_key,
        node_key,
    )
    return validate_interactive_visual_html(html)


def _html_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def generate_interactive_visual_for_node(
    task_id: str,
    node_id: str,
    node: dict,
    subject: str = "",
    grade: str = "",
) -> Optional[str]:
    """Generate one sandbox-safe interactive HTML document for a node."""
    prompt = (node.get("visual_aid_prompt") or "").strip()
    if not prompt or node.get("visual_aid_type", "") == "none":
        return None

    if _use_fake_api():
        return _fallback_fake_html(node)

    try:
        llm = _get_generator_llm()(
            temperature=0.2,
            model_name=(INTERACTIVE_VISUAL_MODEL_NAME or None),
        )
        response = llm.invoke(_build_visual_prompt(node, subject, grade))
        return validate_interactive_visual_html(response.content)
    except Exception:
        logger.exception(
            "Interactive visual generation failed for node %s in task %s",
            node_id,
            task_id,
        )
        return None


def _collect_visual_jobs(questions: List[dict]) -> List[Tuple[dict, str]]:
    jobs: List[Tuple[dict, str]] = []
    for node in questions or []:
        node_id = node.get("id", "")
        if not node_id:
            continue
        if node.get("visual_aid_type", "") == "none":
            continue
        prompt = node.get("visual_aid_prompt", "")
        if prompt and prompt.strip():
            jobs.append((node, node_id))
    return jobs


def _resolve_worker_count(job_count: int, max_workers: Optional[int] = None) -> int:
    if max_workers is None:
        max_workers = INTERACTIVE_VISUAL_MAX_WORKERS
    try:
        worker_count = max(1, int(max_workers or 5))
    except (TypeError, ValueError):
        worker_count = 5
    return min(worker_count, max(1, job_count))


def generate_interactive_visuals_for_questions(
    task_id: str,
    questions: List[dict],
    subject: str = "",
    grade: str = "",
    max_workers: Optional[int] = None,
) -> Dict[str, str]:
    """Generate interactive visuals concurrently and write HTML back to nodes."""
    jobs = _collect_visual_jobs(questions)
    results: Dict[str, str] = {}
    if not jobs:
        return results

    worker_count = _resolve_worker_count(len(jobs), max_workers=max_workers)

    if worker_count == 1:
        for node, node_id in jobs:
            html = generate_interactive_visual_for_node(task_id, node_id, node, subject, grade)
            if html:
                node["visual_aid_html"] = html
                node["visual_aid_urls"] = []
                results[node_id] = html
        return results

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = {
            pool.submit(generate_interactive_visual_for_node, task_id, node_id, node, subject, grade): (node, node_id)
            for node, node_id in jobs
        }
        for fut in as_completed(futures):
            node, node_id = futures[fut]
            try:
                html = fut.result()
            except Exception:
                logger.exception("Interactive visual worker failed for node %s", node_id)
                html = None
            if html:
                node["visual_aid_html"] = html
                node["visual_aid_urls"] = []
                results[node_id] = html

    return results
