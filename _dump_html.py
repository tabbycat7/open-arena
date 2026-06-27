"""Dump visual_aid_html of each node to files for inspection."""
import json
import os
from urllib.parse import urlparse

import pymysql

import config

TASK_ID = "93834be8-a0f2-4fad-9739-903434b566d7"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_html_dump")
os.makedirs(OUT, exist_ok=True)

parsed = urlparse(config.SQLALCHEMY_DATABASE_URI)
conn = pymysql.connect(
    host=parsed.hostname or "127.0.0.1",
    port=parsed.port or 3306,
    user=parsed.username or "root",
    password=parsed.password or "",
    database=config.TEACHING_MAP_MYSQL_DB,
    charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
)
with conn.cursor() as cur:
    cur.execute("SELECT result_json FROM history WHERE id=%s", (TASK_ID,))
    tm = json.loads(cur.fetchone()["result_json"])
conn.close()

for n in tm.get("nodes", []):
    html = n.get("visual_aid_html")
    if not html:
        continue
    qid = n.get("id")
    qtype = n.get("question_type") or "main"
    fn = os.path.join(OUT, "%s_%s.html" % (qtype, qid))
    with open(fn, "w", encoding="utf-8") as f:
        f.write(html)
    print("%-8s %-6s len=%d -> %s" % (qtype, qid, len(html), fn))
