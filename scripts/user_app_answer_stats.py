#!/usr/bin/env python3
"""
按注册用户汇总三个应用会话数量（仅输出：辩论会话、教案会话、教学导航仪次数）。

数据口径：debate_session_owners.user_id、lesson_session_owners.user_id、
teaching_maps.history.user_id。

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
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, display_name FROM users ORDER BY id ASC"
            )
            users: List[Dict[str, Any]] = list(cur.fetchall())

            cur.execute(
                """
                SELECT u.id AS user_id, COUNT(DISTINCT t.session_id) AS debate_sessions
                FROM users u
                LEFT JOIN debate_session_owners o ON o.user_id = u.id
                LEFT JOIN debate_sessions t ON t.session_id = o.session_id
                GROUP BY u.id
                """
            )
            debate_by_uid = {r["user_id"]: r for r in cur.fetchall()}

            cur.execute(
                """
                SELECT u.id AS user_id, COUNT(DISTINCT s.session_id) AS lesson_sessions
                FROM users u
                LEFT JOIN lesson_session_owners o ON o.user_id = u.id
                LEFT JOIN lesson_sessions s ON s.session_id = o.session_id
                GROUP BY u.id
                """
            )
            lesson_by_uid = {r["user_id"]: r for r in cur.fetchall()}

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
                    SELECT user_id, COUNT(*) AS mat_runs
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
                "debate_sessions": int(d.get("debate_sessions") or 0),
                "lesson_sessions": int(l.get("lesson_sessions") or 0),
                "mat_runs": int(m.get("mat_runs") or 0),
            }
        )

    fieldnames = ["user_id", "username", "debate_sessions", "lesson_sessions", "mat_runs"]

    if args.csv:
        w = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        w.writeheader()
        for row in rows_out:
            w.writerow({k: row[k] for k in fieldnames})
        return

    headers = ["user_id", "username", "辩论会话", "教案会话", "导航仪次数"]
    col_keys = ["user_id", "username", "debate_sessions", "lesson_sessions", "mat_runs"]
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
