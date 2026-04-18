#!/usr/bin/env python3
"""
用「教案竞技场」归属表里的 visitor_id（浏览器 Cookie）→ user_id 映射，
回填「辩论场」归属表里仍为空的 user_id。

前提：用户已登录并访问过教案设计竞技场，lesson_session_owners 中该 visitor_id
已写入 user_id；同一访客在辩论场产生的 debate_session_owners 往往共用同一 Cookie，
即可据此补全辩论侧的 user_id。

规则：
  - 只处理 debate_session_owners.user_id IS NULL 的行；
  - 对每个 visitor_id，在 lesson_session_owners 中取 user_id 非空记录里 created_at
    最新的一条作为该 Cookie 对应的用户（若历史上同一 Cookie 曾对应多个 user_id，
    仍会采用最新一条，并在 stderr 提示冲突）。

默认仅预演（打印将更新条数与示例）；写入数据库需加 --apply。

用法（在项目根目录）：

    python scripts/backfill_debate_user_id_from_lesson_visitors.py
    python scripts/backfill_debate_user_id_from_lesson_visitors.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

try:
    import pymysql
except ImportError:
    print("请先安装依赖: pip install pymysql", file=sys.stderr)
    sys.exit(1)

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _database_url() -> str:
    try:
        import config

        return (config.SQLALCHEMY_DATABASE_URI or "").strip()
    except ImportError:
        from dotenv import load_dotenv

        load_dotenv(os.path.join(_ROOT, ".env"))
        return (os.getenv("DATABASE_URL") or "").strip()


def _parse_mysql_url(url: str) -> Tuple[str, int, str, str, str]:
    if not url:
        raise SystemExit("未配置数据库：请在 .env 中设置 DATABASE_URL，或与 app 相同方式加载 config。")
    parsed = urlparse(url)
    db = (parsed.path or "").lstrip("/").split("?")[0]
    if not db:
        raise SystemExit("DATABASE_URL 中缺少数据库名")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 3306
    user = parsed.username or "root"
    password = parsed.password or ""
    return host, port, user, password, db


def _connect(host: str, port: int, user: str, password: str, database: str):
    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def _build_visitor_user_map(cur) -> Tuple[Dict[str, int], Dict[str, Set[int]]]:
    """visitor_id -> 最新一条非空 user_id；以及每个 visitor_id 出现过的所有 user_id（用于冲突提示）。"""
    cur.execute(
        """
        SELECT visitor_id, user_id, created_at
        FROM lesson_session_owners
        WHERE user_id IS NOT NULL
        ORDER BY created_at DESC
        """
    )
    rows: List[Dict[str, Any]] = list(cur.fetchall())
    latest: Dict[str, int] = {}
    all_uids: Dict[str, Set[int]] = defaultdict(set)
    for r in rows:
        vid = (r.get("visitor_id") or "").strip()
        if not vid:
            continue
        uid = int(r["user_id"])
        all_uids[vid].add(uid)
        if vid not in latest:
            latest[vid] = uid
    return latest, all_uids


def main() -> None:
    ap = argparse.ArgumentParser(
        description="根据 lesson_session_owners 的 visitor_id→user_id 回填 debate_session_owners.user_id"
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="执行 UPDATE；不加此参数则只预演",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="仅处理前 N 条待更新辩论归属（0 表示不限制，用于测试）",
    )
    args = ap.parse_args()

    url = _database_url()
    host, port, user, password, db_name = _parse_mysql_url(url)
    conn = _connect(host, port, user, password, db_name)

    try:
        with conn.cursor() as cur:
            latest, all_uids = _build_visitor_user_map(cur)
            if not latest:
                print("lesson_session_owners 中没有任何带 user_id 的记录，无法建立映射。请先让用户登录并访问教案竞技场。")
                return

            multi = {vid: uids for vid, uids in all_uids.items() if len(uids) > 1}
            if multi:
                print(
                    f"提示：以下 visitor_id 在教案表中曾对应多个 user_id（将按最新 created_at 选用其一）：共 {len(multi)} 个",
                    file=sys.stderr,
                )
                for vid, uids in list(multi.items())[:10]:
                    print(f"  {vid[:8]}… -> {sorted(uids)}", file=sys.stderr)
                if len(multi) > 10:
                    print(f"  … 另有 {len(multi) - 10} 个", file=sys.stderr)

            cur.execute(
                """
                SELECT session_id, visitor_id
                FROM debate_session_owners
                WHERE user_id IS NULL
                """
            )
            candidates: List[Tuple[str, str, int]] = []
            for r in cur.fetchall():
                vid = (r.get("visitor_id") or "").strip()
                sid = r.get("session_id")
                if not vid or not sid:
                    continue
                uid = latest.get(vid)
                if uid is not None:
                    candidates.append((sid, vid, uid))

        if args.limit > 0:
            candidates = candidates[: args.limit]

        print(f"lesson 中有 user_id 的不同 visitor 数: {len(latest)}")
        print(f"辩论归属中 user_id 为空、且可在 lesson 映射到的行数: {len(candidates)}")

        if not candidates:
            print("无需更新。")
            return

        for sid, vid, uid in candidates[:5]:
            print(f"  示例 session_id={sid} visitor_id={vid[:8]}… -> user_id={uid}")
        if len(candidates) > 5:
            print(f"  … 共 {len(candidates)} 条")

        if not args.apply:
            print("\n预演结束。确认无误后执行: python scripts/backfill_debate_user_id_from_lesson_visitors.py --apply")
            return

        n = 0
        with conn.cursor() as cur:
            for sid, _vid, uid in candidates:
                cur.execute(
                    """
                    UPDATE debate_session_owners
                    SET user_id = %s
                    WHERE session_id = %s AND user_id IS NULL
                    """,
                    (uid, sid),
                )
                n += cur.rowcount
        conn.commit()
        print(f"\n已提交：实际更新行数（仅统计 rowcount）: {n}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
