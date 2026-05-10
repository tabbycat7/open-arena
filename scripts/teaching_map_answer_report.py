#!/usr/bin/env python3
"""
导出教学地图导航仪作答报告。

默认读取项目根目录 .env 中的 DATABASE_URL 和 TEACHING_MAP_MYSQL_DB，
按学生分组输出 Markdown，便于老师查看每一次提交和平台生成结果。

用法：
  python scripts/teaching_map_answer_report.py
  python scripts/teaching_map_answer_report.py --output teaching_map_report.md
  python scripts/teaching_map_answer_report.py --user 3
  python scripts/teaching_map_answer_report.py --username zhangsan --limit 5 --include-logs
  python scripts/teaching_map_answer_report.py --csv > teaching_map_summary.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def import_pymysql():
    try:
        import pymysql  # type: ignore
    except ImportError:
        print("请先安装依赖: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)
    return pymysql


def parse_mysql_url(url: str) -> Tuple[str, int, str, str, str]:
    if not url.strip():
        raise SystemExit("未设置 DATABASE_URL。请在 .env 中配置，或运行时传入环境变量。")
    parsed = urlparse(url)
    if parsed.scheme and not parsed.scheme.startswith("mysql"):
        raise SystemExit(f"当前脚本只支持 MySQL DATABASE_URL，实际为: {parsed.scheme}")
    database = (parsed.path or "").lstrip("/").split("?")[0]
    if not database:
        raise SystemExit("DATABASE_URL 中缺少数据库名。")
    return (
        parsed.hostname or "127.0.0.1",
        parsed.port or 3306,
        parsed.username or "root",
        parsed.password or "",
        database,
    )


def connect_mysql(host: str, port: int, user: str, password: str, database: str):
    pymysql = import_pymysql()
    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value)


def one_line(value: Any, max_chars: int = 120) -> str:
    text = re.sub(r"\s+", " ", as_text(value)).strip()
    if max_chars > 0 and len(text) > max_chars:
        return text[: max_chars - 1] + "…"
    return text


def md_escape(text: Any) -> str:
    return as_text(text).replace("\\", "\\\\").replace("|", "\\|")


def parse_json(raw: Any, fallback: Any = None) -> Any:
    if raw in (None, ""):
        return fallback
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return fallback


def load_users(conn) -> Dict[int, Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, username, display_name FROM users ORDER BY id ASC")
        return {int(row["id"]): row for row in cur.fetchall()}


def build_history_query(args: argparse.Namespace) -> Tuple[str, List[Any]]:
    where = []
    params: List[Any] = []
    if args.user is not None:
        where.append("user_id = %s")
        params.append(args.user)
    if args.from_date:
        where.append("created_at >= %s")
        params.append(f"{args.from_date} 00:00:00")
    if args.to_date:
        where.append("created_at <= %s")
        params.append(f"{args.to_date} 23:59:59")

    sql = (
        "SELECT id, user_id, user_display_name, subject, grade, teaching_goals, "
        "student_profile, difficulty_analysis, language_style, model_id, "
        "duration_seconds, result_json, created_at "
        "FROM history"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC"
    if args.limit and args.limit > 0:
        sql += " LIMIT %s"
        params.append(args.limit)
    return sql, params


def load_history(conn, args: argparse.Namespace) -> List[Dict[str, Any]]:
    sql, params = build_history_query(args)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = list(cur.fetchall())
    for row in rows:
        row["created_at_text"] = as_text(row.get("created_at"))
        row["result"] = parse_json(row.pop("result_json", None), {"nodes": [], "edges": []})
    return rows


def load_agent_logs(conn, task_ids: Iterable[str]) -> Dict[str, List[Dict[str, Any]]]:
    task_ids = [tid for tid in task_ids if tid]
    if not task_ids:
        return {}
    placeholders = ",".join(["%s"] * len(task_ids))
    with conn.cursor() as cur:
        cur.execute(
            "SELECT task_id, step_number, agent_name, output_json, created_at "
            f"FROM agent_logs WHERE task_id IN ({placeholders}) "
            "ORDER BY task_id ASC, step_number ASC",
            task_ids,
        )
        rows = list(cur.fetchall())
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        row["output"] = parse_json(row.pop("output_json", None), {})
        grouped[str(row["task_id"])].append(row)
    return grouped


def display_user(row: Dict[str, Any], users: Dict[int, Dict[str, Any]]) -> Tuple[str, str]:
    uid = row.get("user_id")
    if uid is not None:
        user = users.get(int(uid), {})
        username = user.get("username") or ""
        display_name = user.get("display_name") or row.get("user_display_name") or username
        label = display_name or f"用户 {uid}"
        if username and username != label:
            label = f"{label}（{username}）"
        return str(uid), label
    fallback = row.get("user_display_name") or "未登录/未知学生"
    return "未绑定", as_text(fallback)


def nodes_by_type(result: Dict[str, Any]) -> Tuple[List[dict], List[dict], List[dict], List[dict]]:
    nodes = result.get("nodes") if isinstance(result, dict) else []
    if not isinstance(nodes, list):
        nodes = []
    main_nodes = [n for n in nodes if n.get("question_type") == "main"]
    variant_nodes = [n for n in nodes if n.get("question_type") == "variant"]
    scaffold_nodes = [n for n in nodes if n.get("question_type") == "scaffold"]
    main_nodes.sort(key=lambda n: natural_key(n.get("id", "")))
    variant_nodes.sort(key=lambda n: natural_key(n.get("id", "")))
    scaffold_nodes.sort(key=lambda n: natural_key(n.get("id", "")))
    return nodes, main_nodes, variant_nodes, scaffold_nodes


def natural_key(value: Any) -> Tuple[Any, ...]:
    parts = re.split(r"(\d+)", as_text(value))
    return tuple(int(p) if p.isdigit() else p for p in parts)


def node_commentary(node: Dict[str, Any]) -> str:
    return (
        node.get("lesson_presentation_script")
        or node.get("commentary")
        or node.get("Commentary")
        or ""
    )


def node_meta(node: Dict[str, Any]) -> List[str]:
    meta = []
    knowledge = node.get("knowledge_points") or []
    if isinstance(knowledge, list) and knowledge:
        meta.append("知识点：" + "、".join(as_text(x) for x in knowledge))
    elif isinstance(knowledge, str) and knowledge.strip():
        meta.append("知识点：" + knowledge.strip())
    cognitive = node.get("cognitive_level") or node.get("bloom_level")
    if cognitive not in (None, ""):
        meta.append("认知层次：" + as_text(cognitive))
    difficulty = node.get("difficulty")
    if difficulty not in (None, ""):
        meta.append("难度：" + as_text(difficulty))
    design = node.get("design_intent") or node.get("design_rationale")
    if design:
        meta.append("设计意图：" + one_line(design, 180))
    return meta


def append_node_md(lines: List[str], node: Dict[str, Any], indent: str = "") -> None:
    node_id = as_text(node.get("id") or "未编号")
    content = as_text(node.get("content") or "").strip() or "（无内容）"
    lines.append(f"{indent}- `{node_id}` {content}")
    meta = node_meta(node)
    if meta:
        lines.append(f"{indent}  - " + "；".join(meta))
    commentary = one_line(node_commentary(node), 240)
    if commentary:
        lines.append(f"{indent}  - 说课稿：{commentary}")
    bridge = one_line(node.get("bridge_function"), 180)
    if bridge:
        lines.append(f"{indent}  - 桥梁功能：{bridge}")


def append_result_md(lines: List[str], result: Dict[str, Any]) -> None:
    nodes, main_nodes, variant_nodes, scaffold_nodes = nodes_by_type(result)
    edges = result.get("edges") if isinstance(result, dict) else []
    edge_count = len(edges) if isinstance(edges, list) else 0
    lines.append(
        f"- 生成结果概览：共 {len(nodes)} 个问题节点（主干 {len(main_nodes)}、"
        f"变式 {len(variant_nodes)}、支架 {len(scaffold_nodes)}），{edge_count} 条连接关系。"
    )
    if not nodes:
        lines.append("- 生成结果为空或无法解析。")
        return

    variants_by_main: Dict[str, List[dict]] = defaultdict(list)
    for node in variant_nodes:
        main_id = as_text(node.get("main_id") or node.get("parent_id"))
        variants_by_main[main_id].append(node)

    scaffolds_by_pair: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    loose_scaffolds: List[dict] = []
    for node in scaffold_nodes:
        from_id = as_text(node.get("from_id") or node.get("from_main_id"))
        to_id = as_text(node.get("to_id") or node.get("to_main_id"))
        if from_id or to_id:
            scaffolds_by_pair[(from_id, to_id)].append(node)
        else:
            loose_scaffolds.append(node)

    lines.append("")
    lines.append("生成的问题链：")
    for index, node in enumerate(main_nodes, 1):
        lines.append(f"{index}. 主干问题")
        append_node_md(lines, node, "   ")
        related_variants = variants_by_main.get(as_text(node.get("id")), [])
        if related_variants:
            lines.append("   - 关联变式：")
            for variant in related_variants:
                append_node_md(lines, variant, "     ")
        next_node = main_nodes[index] if index < len(main_nodes) else None
        if next_node:
            pair_scaffolds = (
                scaffolds_by_pair.get((as_text(node.get("id")), as_text(next_node.get("id"))), [])
                or scaffolds_by_pair.get((as_text(node.get("id")), ""), [])
                or scaffolds_by_pair.get(("", as_text(next_node.get("id"))), [])
            )
            if pair_scaffolds:
                lines.append("   - 过渡支架：")
                for scaffold in pair_scaffolds:
                    append_node_md(lines, scaffold, "     ")
    if loose_scaffolds:
        lines.append("")
        lines.append("未关联支架问题：")
        for scaffold in loose_scaffolds:
            append_node_md(lines, scaffold)


def append_logs_md(lines: List[str], logs: List[Dict[str, Any]]) -> None:
    if not logs:
        lines.append("- Agent 过程记录：无")
        return
    lines.append("- Agent 过程记录：")
    for log in logs:
        output = log.get("output") or {}
        preview = ""
        if isinstance(output, dict):
            output_preview = output.get("output_preview") or {}
            if isinstance(output_preview, dict):
                preview = ", ".join(
                    f"{key}={one_line(value, 60)}"
                    for key, value in output_preview.items()
                    if value not in (None, "", [], {})
                )
            if not preview:
                preview = one_line(json.dumps(output, ensure_ascii=False), 160)
        lines.append(
            f"  - 第 {log.get('step_number')} 步：{log.get('agent_name')} "
            f"({as_text(log.get('created_at'))}) {preview}"
        )


def render_markdown(
    rows: List[Dict[str, Any]],
    users: Dict[int, Dict[str, Any]],
    logs_by_task: Dict[str, List[Dict[str, Any]]],
) -> str:
    lines = [
        "# 教学地图导航仪作答报告",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"记录数：{len(rows)}",
        "",
    ]
    if not rows:
        lines.append("没有查询到符合条件的记录。")
        return "\n".join(lines) + "\n"

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    labels: Dict[str, str] = {}
    for row in rows:
        user_key, label = display_user(row, users)
        grouped[user_key].append(row)
        labels[user_key] = label

    for user_key in sorted(grouped, key=lambda x: (x == "未绑定", natural_key(x))):
        user_rows = grouped[user_key]
        lines.append(f"## {labels[user_key]}")
        lines.append("")
        lines.append(f"- 用户 ID：{user_key}")
        lines.append(f"- 提交次数：{len(user_rows)}")
        lines.append("")
        for idx, row in enumerate(user_rows, 1):
            task_id = as_text(row.get("id"))
            lines.append(f"### 第 {idx} 次提交")
            lines.append("")
            lines.append(f"- 任务 ID：`{task_id}`")
            lines.append(f"- 提交时间：{row.get('created_at_text') or ''}")
            lines.append(f"- 学科/年级：{row.get('subject') or '未填写'} / {row.get('grade') or '未填写'}")
            lines.append(f"- 模型：{row.get('model_id') or '未知'}")
            duration = row.get("duration_seconds")
            if duration not in (None, ""):
                lines.append(f"- 生成耗时：{round(float(duration), 2)} 秒")
            if row.get("language_style"):
                lines.append(f"- 语言风格：{row.get('language_style')}")
            lines.append("")
            lines.append("学生输入：")
            lines.append(f"- 教学目标：{one_line(row.get('teaching_goals'), 500) or '未填写'}")
            lines.append(f"- 学情描述：{one_line(row.get('student_profile'), 500) or '未填写'}")
            if row.get("difficulty_analysis"):
                lines.append(f"- 重难点分析：{one_line(row.get('difficulty_analysis'), 500)}")
            lines.append("")
            append_result_md(lines, row.get("result") or {})
            if task_id in logs_by_task:
                lines.append("")
                append_logs_md(lines, logs_by_task[task_id])
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_csv(rows: List[Dict[str, Any]], users: Dict[int, Dict[str, Any]]) -> None:
    fieldnames = [
        "user_id",
        "student",
        "task_id",
        "created_at",
        "subject",
        "grade",
        "model_id",
        "duration_seconds",
        "main_count",
        "variant_count",
        "scaffold_count",
        "node_count",
        "teaching_goals",
        "student_profile",
    ]
    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        user_key, label = display_user(row, users)
        nodes, main_nodes, variant_nodes, scaffold_nodes = nodes_by_type(row.get("result") or {})
        writer.writerow(
            {
                "user_id": user_key,
                "student": label,
                "task_id": row.get("id") or "",
                "created_at": row.get("created_at_text") or "",
                "subject": row.get("subject") or "",
                "grade": row.get("grade") or "",
                "model_id": row.get("model_id") or "",
                "duration_seconds": row.get("duration_seconds") or "",
                "main_count": len(main_nodes),
                "variant_count": len(variant_nodes),
                "scaffold_count": len(scaffold_nodes),
                "node_count": len(nodes),
                "teaching_goals": one_line(row.get("teaching_goals"), 0),
                "student_profile": one_line(row.get("student_profile"), 0),
            }
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出教学地图导航仪学生作答与生成结果")
    parser.add_argument("--user", type=int, help="只查看指定 user_id")
    parser.add_argument("--username", help="按 users.username 精确筛选")
    parser.add_argument("--limit", type=int, default=0, help="最多读取多少条记录，0 表示不限制")
    parser.add_argument("--from-date", help="开始日期，格式 YYYY-MM-DD")
    parser.add_argument("--to-date", help="结束日期，格式 YYYY-MM-DD")
    parser.add_argument("--include-logs", action="store_true", help="在 Markdown 中附带 Agent 过程记录摘要")
    parser.add_argument("--csv", action="store_true", help="输出 CSV 摘要，而不是 Markdown 全文报告")
    parser.add_argument("--output", "-o", help="Markdown 输出文件路径；不填则输出到终端")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if load_dotenv:
        load_dotenv(os.path.join(ROOT_DIR, ".env"))

    host, port, user, password, main_db = parse_mysql_url(os.getenv("DATABASE_URL", ""))
    mat_db = (os.getenv("TEACHING_MAP_MYSQL_DB") or "teaching_maps").strip()

    main_conn = connect_mysql(host, port, user, password, main_db)
    try:
        users = load_users(main_conn)
    finally:
        main_conn.close()

    if args.username:
        matched = [uid for uid, row in users.items() if row.get("username") == args.username]
        if not matched:
            raise SystemExit(f"没有找到 username={args.username!r} 的用户。")
        args.user = matched[0]

    mat_conn = connect_mysql(host, port, user, password, mat_db)
    try:
        rows = load_history(mat_conn, args)
        logs_by_task = load_agent_logs(mat_conn, [r.get("id") for r in rows]) if args.include_logs else {}
    finally:
        mat_conn.close()

    if args.csv:
        write_csv(rows, users)
        return

    report = render_markdown(rows, users, logs_by_task)
    if args.output:
        output_path = os.path.abspath(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"已生成报告：{output_path}")
    else:
        print(report)


if __name__ == "__main__":
    main()
