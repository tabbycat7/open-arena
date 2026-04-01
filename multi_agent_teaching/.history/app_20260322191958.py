"""Flask application — serves the UI and orchestrates the LangGraph workflow."""
from __future__ import annotations

import json
import sys
import os
import time
import uuid
import threading
import traceback
from typing import Dict, List, Optional
from datetime import datetime

import pymysql
from flask import Flask, render_template, request, jsonify, Response, stream_with_context

sys.path.insert(0, os.path.dirname(__file__))

from agents.graph import build_graph
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB

app = Flask(__name__)

# In-memory task store (live progress only)
tasks: Dict[str, dict] = {}


# ---------------------------------------------------------------------------
# MySQL helpers
# ---------------------------------------------------------------------------

def _get_conn():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def _init_db():
    print("[DB] 正在检查 MySQL 连接 (%s:%s)..." % (MYSQL_HOST, MYSQL_PORT))
    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            charset="utf8mb4",
        )
    except pymysql.err.OperationalError as e:
        print("[DB] MySQL 连接失败: %s" % e)
        print("[DB] 请检查:")
        print("     1. MySQL 服务是否已启动")
        print("     2. .env 中 MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD 是否正确")
        raise SystemExit(1)

    with conn.cursor() as cur:
        cur.execute("SHOW DATABASES LIKE %s", (MYSQL_DB,))
        exists = cur.fetchone()
        if not exists:
            print("[DB] 数据库 `%s` 不存在，正在创建..." % MYSQL_DB)
            cur.execute(
                "CREATE DATABASE `%s` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci" % MYSQL_DB
            )
            print("[DB] 数据库 `%s` 创建成功" % MYSQL_DB)
        else:
            print("[DB] 数据库 `%s` 已存在" % MYSQL_DB)
    conn.commit()
    conn.close()

    conn = _get_conn()
    with conn.cursor() as cur:
        # history 表
        cur.execute("SHOW TABLES LIKE 'history'")
        exists = cur.fetchone()
        if not exists:
            print("[DB] 表 `history` 不存在，正在创建...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id              VARCHAR(64) PRIMARY KEY,
                subject         VARCHAR(32),
                grade           VARCHAR(32),
                teaching_goals  TEXT,
                student_profile TEXT,
                language_style  VARCHAR(32),
                result_json     LONGTEXT,
                created_at      DATETIME,
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        if not exists:
            print("[DB] 表 `history` 创建成功")
        else:
            print("[DB] 表 `history` 已存在")

        # agent_logs 表
        cur.execute("SHOW TABLES LIKE 'agent_logs'")
        exists = cur.fetchone()
        if not exists:
            print("[DB] 表 `agent_logs` 不存在，正在创建...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agent_logs (
                id              INT AUTO_INCREMENT PRIMARY KEY,
                task_id         VARCHAR(64) NOT NULL,
                step_number     INT NOT NULL,
                agent_name      VARCHAR(64) NOT NULL,
                output_json     LONGTEXT,
                created_at      DATETIME,
                INDEX idx_task_id (task_id),
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        if not exists:
            print("[DB] 表 `agent_logs` 创建成功")
        else:
            print("[DB] 表 `agent_logs` 已存在")

    conn.commit()
    conn.close()
    print("[DB] 数据库初始化完成")


def _save_to_db(task_id: str, inputs: dict, result: dict):
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "REPLACE INTO history (id, subject, grade, teaching_goals, student_profile, language_style, result_json, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                task_id,
                inputs.get("subject", ""),
                inputs.get("grade", ""),
                inputs.get("teaching_goals", ""),
                inputs.get("student_profile", ""),
                inputs.get("language_style", ""),
                json.dumps(result, ensure_ascii=False),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
    conn.commit()
    conn.close()


def _save_agent_log(task_id: str, step_number: int, agent_name: str, output: dict):
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO agent_logs (task_id, step_number, agent_name, output_json, created_at) VALUES (%s, %s, %s, %s, %s)",
            (
                task_id,
                step_number,
                agent_name,
                json.dumps(output, ensure_ascii=False, default=str),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
    conn.commit()
    conn.close()


def _get_agent_logs(task_id: str) -> List[dict]:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, step_number, agent_name, output_json, created_at FROM agent_logs WHERE task_id = %s ORDER BY step_number ASC",
            (task_id,),
        )
        rows = cur.fetchall()
    conn.close()
    for r in rows:
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        if r.get("output_json"):
            try:
                r["output"] = json.loads(r.pop("output_json"))
            except json.JSONDecodeError:
                r["output"] = r.pop("output_json")
    return rows


def _get_history(limit: int = 50) -> List[dict]:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, subject, grade, teaching_goals, language_style, created_at FROM history ORDER BY created_at DESC LIMIT %s",
            (limit,),
        )
        rows = cur.fetchall()
    conn.close()
    for r in rows:
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].strftime("%Y-%m-%d %H:%M:%S")
    return rows


def _get_history_detail(record_id: str) -> Optional[dict]:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM history WHERE id = %s", (record_id,))
        row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    if isinstance(row.get("created_at"), datetime):
        row["created_at"] = row["created_at"].strftime("%Y-%m-%d %H:%M:%S")
    row["result"] = json.loads(row.pop("result_json"))
    return row


_init_db()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.form
    attachment_text = ""
    if "attachment" in request.files:
        file = request.files["attachment"]
        if file.filename:
            attachment_text = file.read().decode("utf-8", errors="ignore")

    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "status": "running",
        "progress": [],
        "result": None,
        "input": {
            "subject": data.get("subject", ""),
            "grade": data.get("grade", ""),
            "teaching_goals": data.get("teaching_goals", ""),
            "student_profile": data.get("student_profile", ""),
            "language_style": data.get("language_style", "严谨学术"),
            "attachment": attachment_text,
        },
    }

    thread = threading.Thread(target=_run_workflow, args=(task_id,), daemon=True)
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/api/stream/<task_id>")
def stream(task_id):
    """SSE endpoint — streams progress messages as they arrive."""
    from_idx = request.args.get("from", "0")
    try:
        start_sent = max(int(from_idx), 0)
    except ValueError:
        start_sent = 0

    def event_stream():
        if task_id not in tasks:
            yield "data: %s\n\n" % json.dumps({"type": "error", "message": "Task not found"}, ensure_ascii=False)
            return

        sent = start_sent

        while True:
            task = tasks[task_id]
            progress = task["progress"]

            if sent > len(progress):
                sent = len(progress)

            while sent < len(progress):
                item = progress[sent]
                if isinstance(item, dict):
                    msg = item.get("message", "")
                    agent = item.get("agent", "")
                    agent_display_name = item.get("agent_display_name", AGENT_NAME_MAP.get(agent, agent))
                    step_number = item.get("step_number", 0)
                    output_preview = item.get("output_preview")
                    input_preview = item.get("input_preview")
                else:
                    msg = item
                    agent = ""
                    agent_display_name = ""
                    step_number = 0
                    output_preview = None
                    input_preview = None
                yield "data: %s\n\n" % json.dumps(
                    {
                        "type": "progress",
                        "message": msg,
                        "agent": agent,
                        "agent_display_name": agent_display_name,
                        "step_number": step_number,
                        "input_preview": input_preview,
                        "output_preview": output_preview,
                    },
                    ensure_ascii=False,
                    default=str,
                )
                sent += 1

            if task["status"] in ("done", "error"):
                payload = {
                    "type": "done" if task["status"] == "done" else "error",
                    "result": task.get("result"),
                    "message": task.get("error_message", ""),
                }
                yield "data: %s\n\n" % json.dumps(payload, ensure_ascii=False, default=str)
                return

            time.sleep(0.5)

    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")


@app.route("/api/result/<task_id>")
def get_result(task_id):
    task = tasks.get(task_id)
    if not task:
        record = _get_history_detail(task_id)
        if record:
            return jsonify({"status": "done", "result": record["result"]})
        return jsonify({"error": "Task not found"}), 404
    if task["status"] == "running":
        return jsonify({"status": "running", "progress": task["progress"]})
    if task["status"] == "error":
        return jsonify({"status": "error", "message": task.get("error_message", "")}), 500
    return jsonify({"status": "done", "result": task["result"]})


@app.route("/api/history")
def history_list():
    return jsonify(_get_history())


@app.route("/api/history/<record_id>")
def history_detail(record_id):
    record = _get_history_detail(record_id)
    if not record:
        return jsonify({"error": "Record not found"}), 404
    return jsonify(record)


@app.route("/api/history/<record_id>", methods=["DELETE"])
def history_delete(record_id):
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM history WHERE id = %s", (record_id,))
        cur.execute("DELETE FROM agent_logs WHERE task_id = %s", (record_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/logs/<task_id>")
def get_logs(task_id):
    logs = _get_agent_logs(task_id)
    return jsonify(logs)


# ---------------------------------------------------------------------------
# Workflow runner
# ---------------------------------------------------------------------------

AGENT_NAME_MAP = {
    "learning_analysis": "学情与目标解析Agent",
    "teaching_logic_design": "教学地图逻辑规划Agent",
    "main_question_chain": "主干问题链构建Agent",
    "cognitive_check": "认知对齐检验Agent(V1)",
    "goal_check": "教学目标对齐检验Agent(V3)",
    "teaching_logic_check": "教学逻辑检验Agent(V5)",
    "aggregate_main_checks": "系统-主干问题检验汇总",
    "fan_out_gen": "系统-并行生成分发",
    "variant_question": "变式问题生成Agent",
    "variant_check": "变式问题检验Agent(V2a)",
    "scaffold_question": "支架问题生成Agent",
    "scaffold_check": "支架问题检验Agent(V2b)",
    "wait_for_both": "系统-两条流水线汇合",
    "map_integration": "教学地图整合Agent",
    "bump_main_retry": "系统-主干问题重试",
    "bump_variant_retry": "系统-变式问题重试",
    "bump_scaffold_retry": "系统-支架问题重试",
}


def _truncate_text(text: str, limit: int = 140) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _safe_preview_value(value):
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, str):
        return _truncate_text(value)
    return _truncate_text(str(value), 220)


def _build_output_preview(output: dict) -> dict:
    return {k: v for k, v in output.items() if k != 'progress_messages'}


def _build_input_preview(node_name: str, accumulated: dict) -> dict:
    INPUT_FIELDS = {
        "learning_analysis": ["subject", "grade", "teaching_goals", "student_profile", "language_style"],
        "teaching_logic_design": ["subject", "grade", "teaching_goals", "analysis_result"],
        "main_question_chain": ["subject", "grade", "teaching_goals", "student_profile", "language_style", "map_construction_logic", "main_retry_count", "validation_results"],
        "cognitive_check": ["subject", "grade", "analysis_result", "main_questions"],
        "goal_check": ["teaching_goals", "analysis_result", "main_questions"],
        "teaching_logic_check": ["subject", "grade", "teaching_goals", "analysis_result", "map_construction_logic", "main_questions"],
        "variant_question": ["subject", "grade", "language_style", "main_questions", "variant_question_plan", "variant_retry_count"],
        "scaffold_question": ["subject", "grade", "language_style", "main_questions", "scaffold_question_plan", "scaffold_retry_count"],
        "variant_check": ["subject", "grade", "language_style", "analysis_result", "teaching_goals", "main_questions", "variant_questions"],
        "scaffold_check": ["subject", "grade", "language_style", "analysis_result", "teaching_goals", "main_questions", "scaffold_questions"],
        "map_integration": ["subject", "grade", "teaching_goals", "analysis_result", "main_questions", "variant_questions", "scaffold_questions"]
    }
    scalar_fields = INPUT_FIELDS.get(node_name, [])
    if not scalar_fields:
        return {k: v for k, v in accumulated.items() if k != "progress_messages"}
    preview = {}
    for f in scalar_fields:
        if f in accumulated:
            preview[f] = accumulated[f]

    if node_name == "main_question_chain" and isinstance(preview.get("map_construction_logic"), dict):
        map_logic = preview["map_construction_logic"]
        preview["map_construction_logic"] = {
            "main_question_chain": map_logic.get("main_question_chain", [])
        }

    return preview


def _run_workflow(task_id: str):
    task = tasks[task_id]
    try:
        graph = build_graph()
        initial_state = {
            **task["input"],
            "main_retry_count": 0,
            "variant_retry_count": 0,
            "scaffold_retry_count": 0,
            "main_checks_done": 0,
            "main_validation_feedback": [],
            "main_failed_validators": [],
            "variant_validation_feedback": [],
            "scaffold_validation_feedback": [],
            "progress_messages": [],
            "validation_results": [],
            "main_questions": [],
            "variant_questions": [],
            "scaffold_questions": [],
            "analysis_result": {},
            "map_construction_logic": {},
            "teaching_map": {"nodes": [], "edges": []},
        }

        accumulated = dict(initial_state)
        stream_config = {"recursion_limit": 100}
        step_number = 0

        for state_snapshot in graph.stream(initial_state, config=stream_config):
            for node_name, node_output in state_snapshot.items():
                if isinstance(node_output, dict):
                    step_number += 1
                    agent_display_name = AGENT_NAME_MAP.get(node_name, node_name)

                    # input_preview 在 accumulated 更新前计算（反映本节点执行前的 state）
                    input_preview = _build_input_preview(node_name, accumulated)
                    new_messages = node_output.get("progress_messages", [])
                    output_preview = _build_output_preview(node_output)

                    progress_item = {
                        "message": new_messages[0] if new_messages else "%s 执行完成" % agent_display_name,
                        "agent": node_name,
                        "agent_display_name": agent_display_name,
                        "step_number": step_number,
                        "input_preview": input_preview,
                        "output_preview": output_preview,
                    }
                    # 若有多条消息，第一条作为主消息，后续追加
                    task["progress"].append(progress_item)
                    for msg in new_messages[1:]:
                        task["progress"].append({
                            **progress_item,
                            "message": msg,
                        })

                    for key, value in node_output.items():
                        if key == "progress_messages":
                            continue
                        accumulated[key] = value

                    log_output = {k: v for k, v in node_output.items() if k != "progress_messages"}
                    try:
                        _save_agent_log(task_id, step_number, agent_display_name, {
                            "input_preview": input_preview,
                            "output": log_output,
                        })
                    except Exception as log_err:
                        print("[LOG] 保存日志失败: %s" % log_err)

        task["result"] = accumulated.get("teaching_map", {"nodes": [], "edges": []})
        _save_to_db(task_id, task["input"], task["result"])
        task["status"] = "done"
        task["progress"].append("[系统] 教学地图生成完成！")

    except Exception as e:
        task["status"] = "error"
        task["error_message"] = str(e)
        task["progress"].append("[错误] %s" % str(e))
        print("[ERROR] Workflow failed: %s" % traceback.format_exc())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
