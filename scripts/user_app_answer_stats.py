#!/usr/bin/env python3
"""
按注册用户汇总三个网页应用的作答与标注情况：

  - 教育观辩论场：debate_session_owners.user_id → debate_sessions / debate_rounds
  - 教案设计竞技场：lesson_session_owners.user_id → lesson_sessions / lesson_chat_rounds
  - 教学导航仪：teaching_maps.history.user_id

应用启动时会执行迁移（见 app._ensure_owner_user_id_schema），为归属表增加 user_id，
并按 teacher_name 与 username/display_name 一致回填旧数据。

用法：
  在项目根目录执行（读取 .env 中的 DATABASE_URL、TEACHING_MAP_MYSQL_DB）：

    python scripts/user_app_answer_stats.py
    python scripts/user_app_answer_stats.py --csv > stats.csv

  或临时指定连接串（注意不要写入版本库）：

    DATABASE_URL='mysql+pymysql://...' python scripts/user_app_answer_stats.py
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

try:
    import pymysql
except ImportError:
    print("请先安装依赖: pip install pymysql python-dotenv", file=sys.stderr)
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore


def _parse_mysql_url(url: str) -> Tuple[str, int, str, str, str]:
    if not url or not url.strip():
        raise SystemExit("未设置 DATABASE_URL（可在 .env 或环境中配置）")
    parsed = urlparse(url)
    db = (parsed.path or "").lstrip("/").split("?")[0]
    if not db:
        raise SystemExit("DATABASE_URL 中缺少数据库名（path 部分）")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 3306
    user = parsed.username or "root"
    password = parsed.password or ""
    return host, port, user, password, db


def _connect(host: str, port: int, user: str, password: str, database: Optional[str] = None):
    kw: Dict[str, Any] = dict(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    if database:
        kw["database"] = database
    return pymysql.connect(**kw)


def main() -> None:
    if load_dotenv:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        load_dotenv(os.path.join(root, ".env"))

    ap = argparse.ArgumentParser(description="按用户汇总三个应用的作答与标注统计")
    ap.add_argument("--csv", action="store_true", help="输出 CSV 而非表格")
    args = ap.parse_args()

    url = os.getenv("DATABASE_URL", "").strip()
    host, port, user, password, main_db = _parse_mysql_url(url)
    mat_db = (os.getenv("TEACHING_MAP_MYSQL_DB") or "teaching_maps").strip()

    conn = _connect(host, port, user, password, main_db)
    debate_unmatched_owners = 0
    lesson_unmatched_owners = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, display_name, created_at FROM users ORDER BY id ASC"
            )
            users: List[Dict[str, Any]] = list(cur.fetchall())

            debate_sql = """
            SELECT
              u.id AS user_id,
              COUNT(DISTINCT t.session_id) AS debate_sessions,
              COUNT(DISTINCT dr.id) AS debate_rounds,
              COUNT(DISTINCT CASE WHEN t.status = 'annotated' THEN t.session_id END) AS debate_status_annotated,
              COUNT(DISTINCT CASE WHEN t.stance_changed IS NOT NULL THEN t.session_id END) AS debate_stance_filled,
              COUNT(DISTINCT CASE
                WHEN t.annotation_note IS NOT NULL AND TRIM(t.annotation_note) <> '' THEN t.session_id
              END) AS debate_has_annotation_note
            FROM users u
            LEFT JOIN debate_session_owners o ON o.user_id = u.id
            LEFT JOIN debate_sessions t ON t.session_id = o.session_id
            LEFT JOIN debate_rounds dr ON dr.session_id = t.session_id
            GROUP BY u.id
            """
            cur.execute(debate_sql)
            debate_by_uid = {r["user_id"]: r for r in cur.fetchall()}

            lesson_sql = """
            SELECT
              u.id AS user_id,
              COUNT(DISTINCT s.session_id) AS lesson_sessions,
              COUNT(DISTINCT lcr.id) AS lesson_chat_rounds,
              COUNT(DISTINCT CASE WHEN s.winner IS NOT NULL AND TRIM(s.winner) <> '' THEN s.session_id END) AS lesson_has_winner,
              COUNT(DISTINCT CASE WHEN s.status = 'voted' THEN s.session_id END) AS lesson_status_voted,
              COUNT(DISTINCT CASE WHEN s.status = 'completed' THEN s.session_id END) AS lesson_status_completed,
              COUNT(DISTINCT CASE WHEN s.status = 'ready' THEN s.session_id END) AS lesson_status_ready
            FROM users u
            LEFT JOIN lesson_session_owners o ON o.user_id = u.id
            LEFT JOIN lesson_sessions s ON s.session_id = o.session_id
            LEFT JOIN lesson_chat_rounds lcr ON lcr.session_id = s.session_id
            GROUP BY u.id
            """
            cur.execute(lesson_sql)
            lesson_by_uid = {r["user_id"]: r for r in cur.fetchall()}

            cur.execute(
                "SELECT COUNT(*) AS c FROM debate_session_owners WHERE user_id IS NULL"
            )
            debate_unmatched_owners = int(cur.fetchone()["c"])
            cur.execute(
                "SELECT COUNT(*) AS c FROM lesson_session_owners WHERE user_id IS NULL"
            )
            lesson_unmatched_owners = int(cur.fetchone()["c"])

    finally:
        conn.close()

    mat_by_uid: Dict[int, Dict[str, Any]] = {}
    try:
        mconn = _connect(host, port, user, password, mat_db)
    except pymysql.err.OperationalError as e:
        print(f"[警告] 无法连接教学导航仪库 `{mat_db}`: {e}", file=sys.stderr)
        mconn = None

    if mconn:
        try:
            with mconn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      user_id,
                      COUNT(*) AS mat_runs,
                      SUM(CASE WHEN result_json IS NOT NULL AND LENGTH(TRIM(result_json)) > 2 THEN 1 ELSE 0 END) AS mat_with_result_json
                    FROM history
                    WHERE user_id IS NOT NULL
                    GROUP BY user_id
                    """
                )
                for r in cur.fetchall():
                    mat_by_uid[int(r["user_id"])] = r
        finally:
            mconn.close()

    rows_out: List[Dict[str, Any]] = []
    for u in users:
        uid = int(u["id"])
        d = debate_by_uid.get(uid, {})
        l = lesson_by_uid.get(uid, {})
        m = mat_by_uid.get(uid, {})
        rows_out.append(
            {
                "user_id": uid,
                "username": u.get("username") or "",
                "display_name": u.get("display_name") or "",
                "debate_sessions": int(d.get("debate_sessions") or 0),
                "debate_rounds": int(d.get("debate_rounds") or 0),
                "debate_annotated_status": int(d.get("debate_status_annotated") or 0),
                "debate_stance_filled_sessions": int(d.get("debate_stance_filled") or 0),
                "debate_has_annotation_note": int(d.get("debate_has_annotation_note") or 0),
                "lesson_sessions": int(l.get("lesson_sessions") or 0),
                "lesson_chat_rounds": int(l.get("lesson_chat_rounds") or 0),
                "lesson_has_winner": int(l.get("lesson_has_winner") or 0),
                "lesson_status_voted": int(l.get("lesson_status_voted") or 0),
                "lesson_status_completed": int(l.get("lesson_status_completed") or 0),
                "lesson_status_ready": int(l.get("lesson_status_ready") or 0),
                "mat_runs": int(m.get("mat_runs") or 0),
                "mat_with_result_json": int(m.get("mat_with_result_json") or 0),
            }
        )

    fieldnames = list(rows_out[0].keys()) if rows_out else []

    if not args.csv:
        print(
            "说明：辩论/教案按 debate_session_owners.user_id、lesson_session_owners.user_id 统计；"
            "教学导航仪按 history.user_id。\n"
            f"归属表中 user_id 仍为空的行：辩论 {debate_unmatched_owners}，教案 {lesson_unmatched_owners} "
            "（多为未登录历史或教师姓名与账号不一致；启动应用后会尝试按姓名回填）。\n"
        )

    if args.csv:
        w = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        w.writeheader()
        for row in rows_out:
            w.writerow(row)
        return

    headers = [
        "user_id",
        "username",
        "display",
        "辩论会话",
        "辩论轮次",
        "辩论已标注状态",
        "立场已填",
        "有备注",
        "教案会话",
        "教案追问轮",
        "教案已选winner",
        "status=voted",
        "status=completed",
        "导航仪次数",
        "导航仪有结果JSON",
    ]
    col_keys = [
        "user_id",
        "username",
        "display_name",
        "debate_sessions",
        "debate_rounds",
        "debate_annotated_status",
        "debate_stance_filled_sessions",
        "debate_has_annotation_note",
        "lesson_sessions",
        "lesson_chat_rounds",
        "lesson_has_winner",
        "lesson_status_voted",
        "lesson_status_completed",
        "mat_runs",
        "mat_with_result_json",
    ]
    widths = [len(h) for h in headers]
    str_rows: List[List[str]] = []
    for row in rows_out:
        cells = [str(row[k]) for k in col_keys]
        for i, c in enumerate(cells):
            widths[i] = max(widths[i], len(c))
        str_rows.append(cells)

    def fmt_line(cells: List[str]) -> str:
        return "  ".join(c.ljust(widths[i]) for i, c in enumerate(cells))

    print(fmt_line(headers))
    print(fmt_line(["-" * w for w in widths]))
    for cells in str_rows:
        print(fmt_line(cells))


if __name__ == "__main__":
    main()
