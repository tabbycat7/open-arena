#!/usr/bin/env python3
"""
导出指定用户的全部数据库数据，并拆出互动网页 HTML。

用法：
  python scripts/export_user_data.py --username 1348194626@qq.com
  python scripts/export_user_data.py --user 1 --output exports/user_1
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

import config  # noqa: E402


def import_pymysql():
    try:
        import pymysql  # type: ignore
    except ImportError:
        print("请先安装依赖: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)
    return pymysql


def connect(database: str):
    pymysql = import_pymysql()
    parsed = urlparse(config.SQLALCHEMY_DATABASE_URI)
    return pymysql.connect(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 3306,
        user=parsed.username or "root",
        password=parsed.password or "",
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(obj, date):
        return obj.strftime("%Y-%m-%d")
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=json_default)


def safe_name(text: str, max_len: int = 40) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_." else "_" for c in text)
    return cleaned[:max_len] or "item"


def parse_result_json(raw: Any) -> Dict[str, Any]:
    if raw in (None, ""):
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}


def export_interactive_html(
    task_id: str,
    result: Dict[str, Any],
    html_root: str,
    upload_root: str,
) -> Dict[str, Any]:
    nodes = result.get("nodes") or []
    task_dir = os.path.join(html_root, task_id)
    os.makedirs(task_dir, exist_ok=True)
    index_items: List[Dict[str, Any]] = []
    html_count = 0

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "node")
        qtype = str(node.get("question_type") or "main")
        html = node.get("visual_aid_html") or ""
        entry: Dict[str, Any] = {
            "node_id": node_id,
            "question_type": qtype,
            "content": node.get("content") or "",
            "visual_aid_type": node.get("visual_aid_type"),
            "has_html": bool(html),
            "html_file": None,
            "image_files": [],
        }
        if html:
            filename = f"{qtype}_{node_id}.html"
            path = os.path.join(task_dir, filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            entry["html_file"] = filename
            html_count += 1

        for url in node.get("visual_aid_urls") or []:
            if not isinstance(url, str):
                continue
            # URLs like /static/uploads/visual_aids/{task_id}/{node}.png
            rel = url.lstrip("/")
            if rel.startswith("static/"):
                src = os.path.join(ROOT_DIR, rel.replace("/", os.sep))
            else:
                src = os.path.join(upload_root, task_id, os.path.basename(url))
            if os.path.isfile(src):
                dest_name = os.path.basename(src)
                dest = os.path.join(task_dir, dest_name)
                shutil.copy2(src, dest)
                entry["image_files"].append(dest_name)

        index_items.append(entry)

    # Copy entire visual_aids folder for this task if present
    src_dir = os.path.join(upload_root, task_id)
    if os.path.isdir(src_dir):
        dest_dir = os.path.join(task_dir, "visual_aids")
        if os.path.isdir(dest_dir):
            shutil.rmtree(dest_dir)
        shutil.copytree(src_dir, dest_dir)

    index_path = os.path.join(task_dir, "index.json")
    write_json(index_path, {"task_id": task_id, "nodes": index_items})

    # Simple browsable index.html
    lines = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>{task_id}</title>",
        "<style>body{font-family:sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem}"
        "a{display:block;margin:.4rem 0}</style></head><body>",
        f"<h1>Task {task_id}</h1><ul>",
    ]
    for item in index_items:
        if item["html_file"]:
            label = f"{item['question_type']} {item['node_id']}"
            preview = (item["content"] or "")[:80].replace("<", "&lt;")
            lines.append(
                f"<li><a href='{item['html_file']}' target='_blank'>{label}</a>"
                f"<small>{preview}</small></li>"
            )
    lines.append("</ul></body></html>")
    with open(os.path.join(task_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return {"html_count": html_count, "node_count": len(nodes)}


def main() -> None:
    parser = argparse.ArgumentParser(description="导出用户全部数据与互动网页")
    parser.add_argument("--username", help="用户名（邮箱常作为用户名）")
    parser.add_argument("--user", type=int, help="用户 ID")
    parser.add_argument(
        "--output",
        default=None,
        help="输出目录（默认 exports/user_<id>_<username>）",
    )
    args = parser.parse_args()

    if not args.username and not args.user:
        parser.error("请指定 --username 或 --user")

    hub_db = urlparse(config.SQLALCHEMY_DATABASE_URI).path.lstrip("/").split("?")[0]
    mat_db = config.TEACHING_MAP_MYSQL_DB
    upload_root = os.path.join(ROOT_DIR, "static", "uploads", "visual_aids")

    hub = connect(hub_db)
    try:
        with hub.cursor() as cur:
            if args.user:
                cur.execute(
                    "SELECT id, username, display_name, created_at FROM users WHERE id=%s",
                    (args.user,),
                )
            else:
                cur.execute(
                    "SELECT id, username, display_name, created_at FROM users WHERE username=%s",
                    (args.username,),
                )
            user = cur.fetchone()
            if not user:
                raise SystemExit("未找到该用户。")
            uid = user["id"]

            cur.execute(
                """
                SELECT s.*
                FROM lesson_sessions s
                JOIN lesson_session_owners o ON o.session_id = s.session_id
                WHERE o.user_id = %s
                ORDER BY s.created_at
                """,
                (uid,),
            )
            lessons = cur.fetchall()
            lesson_ids = [r["session_id"] for r in lessons]
            lesson_rounds: List[Dict[str, Any]] = []
            if lesson_ids:
                placeholders = ",".join(["%s"] * len(lesson_ids))
                cur.execute(
                    f"SELECT * FROM lesson_chat_rounds WHERE session_id IN ({placeholders}) ORDER BY id",
                    lesson_ids,
                )
                lesson_rounds = cur.fetchall()
            cur.execute(
                "SELECT * FROM lesson_session_owners WHERE user_id=%s",
                (uid,),
            )
            lesson_owners = cur.fetchall()

            cur.execute(
                """
                SELECT d.*
                FROM debate_sessions d
                JOIN debate_session_owners o ON o.session_id = d.session_id
                WHERE o.user_id = %s
                ORDER BY d.created_at
                """,
                (uid,),
            )
            debates = cur.fetchall()
            debate_ids = [r["session_id"] for r in debates]
            debate_rounds: List[Dict[str, Any]] = []
            if debate_ids:
                placeholders = ",".join(["%s"] * len(debate_ids))
                cur.execute(
                    f"SELECT * FROM debate_rounds WHERE session_id IN ({placeholders}) ORDER BY id",
                    debate_ids,
                )
                debate_rounds = cur.fetchall()
            cur.execute(
                "SELECT * FROM debate_session_owners WHERE user_id=%s",
                (uid,),
            )
            debate_owners = cur.fetchall()
    finally:
        hub.close()

    mat = connect(mat_db)
    try:
        with mat.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, user_display_name, subject, grade,
                       teaching_goals, student_profile, difficulty_analysis,
                       language_style, model_id, duration_seconds,
                       result_json, created_at
                FROM history
                WHERE user_id = %s
                ORDER BY created_at
                """,
                (uid,),
            )
            history_rows = cur.fetchall()
            task_ids = [r["id"] for r in history_rows]
            agent_logs: List[Dict[str, Any]] = []
            if task_ids:
                placeholders = ",".join(["%s"] * len(task_ids))
                cur.execute(
                    f"""
                    SELECT id, task_id, step_number, agent_name, output_json, created_at
                    FROM agent_logs
                    WHERE task_id IN ({placeholders})
                    ORDER BY task_id, step_number, id
                    """,
                    task_ids,
                )
                agent_logs = cur.fetchall()
    finally:
        mat.close()

    out_name = args.output
    if not out_name:
        uname = safe_name(user["username"])
        out_name = os.path.join("exports", f"user_{uid}_{uname}")
    out_dir = out_name if os.path.isabs(out_name) else os.path.join(ROOT_DIR, out_name)
    os.makedirs(out_dir, exist_ok=True)

    # Strip password if somehow present
    user_public = {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "created_at": user["created_at"],
    }
    write_json(os.path.join(out_dir, "user.json"), user_public)

    write_json(
        os.path.join(out_dir, "lesson", "sessions.json"),
        lessons,
    )
    write_json(
        os.path.join(out_dir, "lesson", "chat_rounds.json"),
        lesson_rounds,
    )
    write_json(
        os.path.join(out_dir, "lesson", "owners.json"),
        lesson_owners,
    )
    write_json(
        os.path.join(out_dir, "debate", "sessions.json"),
        debates,
    )
    write_json(
        os.path.join(out_dir, "debate", "rounds.json"),
        debate_rounds,
    )
    write_json(
        os.path.join(out_dir, "debate", "owners.json"),
        debate_owners,
    )

    history_meta: List[Dict[str, Any]] = []
    html_root = os.path.join(out_dir, "interactive_html")
    history_dir = os.path.join(out_dir, "teaching_maps", "history")
    os.makedirs(history_dir, exist_ok=True)

    total_html = 0
    for row in history_rows:
        task_id = row["id"]
        result = parse_result_json(row.get("result_json"))
        # Full record per task
        record = dict(row)
        record["result_json_parsed"] = result
        # Keep raw string too for fidelity, but avoid huge duplicate in meta
        write_json(os.path.join(history_dir, f"{task_id}.json"), record)

        stats = export_interactive_html(task_id, result, html_root, upload_root)
        total_html += stats["html_count"]

        meta = {k: v for k, v in row.items() if k != "result_json"}
        meta["node_count"] = stats["node_count"]
        meta["html_page_count"] = stats["html_count"]
        meta["result_json_bytes"] = len(row.get("result_json") or "")
        history_meta.append(meta)

    write_json(
        os.path.join(out_dir, "teaching_maps", "history_index.json"),
        history_meta,
    )
    write_json(
        os.path.join(out_dir, "teaching_maps", "agent_logs.json"),
        agent_logs,
    )

    manifest = {
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": user_public,
        "counts": {
            "teaching_map_runs": len(history_rows),
            "agent_log_rows": len(agent_logs),
            "interactive_html_pages": total_html,
            "lesson_sessions": len(lessons),
            "lesson_chat_rounds": len(lesson_rounds),
            "debate_sessions": len(debates),
            "debate_rounds": len(debate_rounds),
        },
        "paths": {
            "user": "user.json",
            "teaching_maps_history": "teaching_maps/history/",
            "teaching_maps_index": "teaching_maps/history_index.json",
            "agent_logs": "teaching_maps/agent_logs.json",
            "interactive_html": "interactive_html/",
            "lesson": "lesson/",
            "debate": "debate/",
        },
    }
    write_json(os.path.join(out_dir, "manifest.json"), manifest)

    # README for humans
    readme = f"""# 用户数据导出

- 用户: {user['username']} (id={uid})
- 显示名: {user.get('display_name') or ''}
- 导出时间: {manifest['exported_at']}

## 统计

- 教学地图提交: {len(history_rows)}
- 互动网页 HTML: {total_html}
- Agent 日志行: {len(agent_logs)}
- 课堂互动会话: {len(lessons)}
- 辩论会话: {len(debates)}

## 目录说明

- `user.json` — 用户基本信息
- `teaching_maps/history/*.json` — 每次教学地图完整记录（含 result_json）
- `teaching_maps/history_index.json` — 提交摘要列表
- `teaching_maps/agent_logs.json` — Agent 执行日志
- `interactive_html/<task_id>/` — 拆出的互动网页（`*.html` + `index.html`）
- `lesson/` / `debate/` — 课堂与辩论数据（若有）
"""
    with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)

    print(json.dumps(manifest["counts"], ensure_ascii=False, indent=2))
    print(f"\n导出完成: {out_dir}")


if __name__ == "__main__":
    main()
