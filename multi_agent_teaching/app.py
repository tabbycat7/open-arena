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
from agents.llm import use_generator_model
from config import (
    MYSQL_HOST,
    MYSQL_PORT,
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_DB,
    LLM_GENERATOR_MODEL_NAME,
    LLM_SELECTABLE_MODEL_IDS,
    LLM_THINKING_SUPPORTED_MODEL_IDS,
    LLM_THINKING_DEFAULT_ENABLED,
    LLM_THINKING_BUDGET_DEFAULT,
    LLM_THINKING_BUDGET_MIN,
    LLM_THINKING_BUDGET_MAX,
    LLM_THINKING_BUDGET_PRESETS,
    LLM_THINKING_BUDGET_DEFAULT_PRESET,
    LLM_DEFAULT_MODEL_ICON,
    LLM_MODEL_ICON_MAP,
)
from attachment_parser import parse_uploaded_attachment

app = Flask(__name__)

# In-memory task store (live progress only)
tasks: Dict[str, dict] = {}


def _supports_thinking(model_id: str) -> bool:
    supported = {
        (item or "").strip()
        for item in (LLM_THINKING_SUPPORTED_MODEL_IDS or [])
        if isinstance(item, str)
    }
    return model_id in supported


def _parse_optional_bool(raw_value) -> Optional[bool]:
    if raw_value is None:
        return None
    value = str(raw_value).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return None


def _normalize_thinking_budget(raw_value) -> int:
    try:
        budget = int(str(raw_value).strip())
    except (TypeError, ValueError):
        budget = int(LLM_THINKING_BUDGET_DEFAULT)

    if budget < int(LLM_THINKING_BUDGET_MIN):
        return int(LLM_THINKING_BUDGET_MIN)
    if budget > int(LLM_THINKING_BUDGET_MAX):
        return int(LLM_THINKING_BUDGET_MAX)
    return budget


def _get_thinking_budget_presets() -> List[dict]:
    min_budget = int(LLM_THINKING_BUDGET_MIN)
    max_budget = int(LLM_THINKING_BUDGET_MAX)
    presets = []
    seen = set()
    for item in LLM_THINKING_BUDGET_PRESETS or []:
        if not isinstance(item, dict):
            continue
        preset_id = str(item.get("id", "")).strip()
        if not preset_id or preset_id in seen:
            continue
        label = str(item.get("label", "")).strip() or preset_id
        try:
            range_min = int(item.get("min", min_budget))
        except (TypeError, ValueError):
            range_min = min_budget
        try:
            range_max = int(item.get("max", max_budget))
        except (TypeError, ValueError):
            range_max = max_budget
        if range_min > range_max:
            range_min, range_max = range_max, range_min
        range_min = max(min_budget, min(range_min, max_budget))
        range_max = max(min_budget, min(range_max, max_budget))
        if range_max < range_min:
            range_max = range_min
        try:
            budget = int(item.get("budget", (range_min + range_max) // 2))
        except (TypeError, ValueError):
            budget = (range_min + range_max) // 2
        budget = max(range_min, min(budget, range_max))
        presets.append(
            {
                "id": preset_id,
                "label": label,
                "min": range_min,
                "max": range_max,
                "budget": budget,
            }
        )
        seen.add(preset_id)

    if presets:
        return presets

    fallback = _normalize_thinking_budget(LLM_THINKING_BUDGET_DEFAULT)
    return [{"id": "balanced", "label": "斟酌", "min": fallback, "max": fallback, "budget": fallback}]


def _get_default_thinking_budget_level(presets: Optional[List[dict]] = None) -> str:
    presets = presets or _get_thinking_budget_presets()
    configured = (LLM_THINKING_BUDGET_DEFAULT_PRESET or "").strip()
    if configured and any(item.get("id") == configured for item in presets):
        return configured

    default_budget = _normalize_thinking_budget(LLM_THINKING_BUDGET_DEFAULT)
    for item in presets:
        if int(item["min"]) <= default_budget <= int(item["max"]):
            return str(item["id"])

    if presets:
        nearest = min(presets, key=lambda item: abs(int(item["budget"]) - default_budget))
        return str(nearest["id"])
    return ""


def _resolve_thinking_budget(raw_level, raw_budget) -> tuple:
    presets = _get_thinking_budget_presets()
    selected_level = (str(raw_level).strip() if raw_level is not None else "")
    matched = None
    for item in presets:
        if item.get("id") == selected_level:
            matched = item
            break

    if matched:
        return int(matched["budget"]), str(matched["id"]), str(matched["label"])

    budget = _normalize_thinking_budget(raw_budget)
    if presets:
        nearest = min(presets, key=lambda item: abs(int(item["budget"]) - budget))
        return budget, str(nearest["id"]), str(nearest["label"])
    return budget, "", ""


def _model_display_name(model_id: str) -> str:
    parts = [p for p in (model_id or "").split("/") if p]
    return parts[-1] if parts else model_id


def _get_model_options() -> List[dict]:
    default_icon = (LLM_DEFAULT_MODEL_ICON or "images/model-icons/model-default.svg").strip().lstrip("/")
    model_ids = []
    seen = set()
    for raw in LLM_SELECTABLE_MODEL_IDS or []:
        if not isinstance(raw, str):
            continue
        model_id = raw.strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        model_ids.append(model_id)

    if not model_ids and (LLM_GENERATOR_MODEL_NAME or "").strip():
        model_ids.append(LLM_GENERATOR_MODEL_NAME.strip())

    options = []
    for model_id in model_ids:
        icon = LLM_MODEL_ICON_MAP.get(model_id, default_icon)
        if not isinstance(icon, str) or not icon.strip():
            icon = default_icon
        options.append(
            {
                "id": model_id,
                "name": _model_display_name(model_id),
                "icon": icon.strip().lstrip("/"),
                "supports_thinking": _supports_thinking(model_id),
            }
        )
    return options


def _get_default_model_id() -> str:
    options = _get_model_options()
    return options[0]["id"] if options else ""


def _get_default_model_option() -> dict:
    options = _get_model_options()
    if options:
        return options[0]
    return {
        "id": "",
        "name": "请选择模型",
        "icon": "images/model-icons/model-default.svg",
    }


def _collect_uploaded_files(files) -> List:
    collected = []
    for key in ("attachment", "attachment[]"):
        for file_storage in files.getlist(key):
            if not file_storage or not getattr(file_storage, "filename", ""):
                continue
            collected.append(file_storage)
    return collected


def _is_attachment_parse_failure(parsed_text: str) -> bool:
    if not parsed_text:
        return True
    failure_markers = (
        "附件解析失败",
        "状态: 附件过大",
        "无法直接解析该文件类型",
    )
    return any(marker in parsed_text for marker in failure_markers)


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
                difficulty_analysis TEXT,
                language_style  VARCHAR(32),
                model_id        VARCHAR(255),
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

        cur.execute("SHOW COLUMNS FROM history LIKE 'difficulty_analysis'")
        if not cur.fetchone():
            print("[DB] 表 `history` 缺少字段 difficulty_analysis，正在补齐...")
            cur.execute("ALTER TABLE history ADD COLUMN difficulty_analysis TEXT AFTER student_profile")
        cur.execute("SHOW COLUMNS FROM history LIKE 'model_id'")
        if not cur.fetchone():
            print("[DB] 表 `history` 缺少字段 model_id，正在补齐...")
            cur.execute("ALTER TABLE history ADD COLUMN model_id VARCHAR(255) AFTER language_style")

    conn.commit()
    conn.close()
    print("[DB] 数据库初始化完成")


def _save_to_db(task_id: str, inputs: dict, result: dict):
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "REPLACE INTO history (id, subject, grade, teaching_goals, student_profile, difficulty_analysis, language_style, model_id, result_json, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                task_id,
                inputs.get("subject", ""),
                inputs.get("grade", ""),
                inputs.get("teaching_goals", ""),
                inputs.get("student_profile", ""),
                inputs.get("difficulty_analysis", ""),
                inputs.get("language_style", ""),
                inputs.get("model_id", ""),
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


def _extract_model_id_from_log_payload(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    input_preview = payload.get("input_preview")
    nested_output = payload.get("output")
    model_id = (
        payload.get("model_id")
        or (input_preview.get("model_id") if isinstance(input_preview, dict) else "")
        or (nested_output.get("model_id") if isinstance(nested_output, dict) else "")
    )
    if model_id is None:
        return ""
    return str(model_id).strip()


def _get_history_model_map(task_ids: List[str]) -> Dict[str, str]:
    ids = [task_id for task_id in task_ids if task_id]
    if not ids:
        return {}

    placeholders = ",".join(["%s"] * len(ids))
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT task_id, step_number, output_json FROM agent_logs WHERE task_id IN (%s) ORDER BY task_id ASC, step_number ASC"
            % placeholders,
            tuple(ids),
        )
        rows = cur.fetchall()
    conn.close()

    model_map: Dict[str, str] = {}
    for row in rows:
        task_id = row.get("task_id")
        if not task_id or task_id in model_map:
            continue
        output_json = row.get("output_json")
        if not output_json:
            continue
        try:
            payload = json.loads(output_json)
        except json.JSONDecodeError:
            continue
        model_id = _extract_model_id_from_log_payload(payload)
        if model_id:
            model_map[task_id] = model_id
    return model_map


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
        r["model_id"] = ""
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        if r.get("output_json"):
            try:
                r["output"] = json.loads(r.pop("output_json"))
            except json.JSONDecodeError:
                r["output"] = r.pop("output_json")
        if isinstance(r.get("output"), dict):
            r["model_id"] = _extract_model_id_from_log_payload(r.get("output"))
    return rows


def _get_history(limit: int = 50) -> List[dict]:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, subject, grade, teaching_goals, student_profile, difficulty_analysis, language_style, model_id, created_at FROM history ORDER BY created_at DESC LIMIT %s",
            (limit,),
        )
        rows = cur.fetchall()
    conn.close()

    model_map = _get_history_model_map([r.get("id") for r in rows])

    for r in rows:
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        model_id = (str(r.get("model_id") or "")).strip()
        if not model_id:
            model_id = model_map.get(r.get("id"), "")
        r["model_id"] = model_id
        r["model_display_name"] = _model_display_name(model_id) if model_id else "未知模型"
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
    default_model_option = _get_default_model_option()
    default_model_supports_thinking = _supports_thinking(default_model_option.get("id", ""))
    thinking_budget_presets = _get_thinking_budget_presets()
    thinking_budget_default_level = _get_default_thinking_budget_level(thinking_budget_presets)
    return render_template(
        "index.html",
        model_options=_get_model_options(),
        default_model_id=_get_default_model_id(),
        default_model_option=default_model_option,
        thinking_default_enabled=bool(LLM_THINKING_DEFAULT_ENABLED and default_model_supports_thinking),
        thinking_budget_default=int(LLM_THINKING_BUDGET_DEFAULT),
        thinking_budget_min=int(LLM_THINKING_BUDGET_MIN),
        thinking_budget_max=int(LLM_THINKING_BUDGET_MAX),
        thinking_budget_presets=thinking_budget_presets,
        thinking_budget_default_level=thinking_budget_default_level,
    )


@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.form
    model_id = (data.get("model_id", "") or "").strip()
    allowed_model_ids = [item["id"] for item in _get_model_options()]
    if not model_id:
        model_id = allowed_model_ids[0] if allowed_model_ids else ""
    if allowed_model_ids and model_id not in allowed_model_ids:
        return jsonify({"error": "所选模型不在可选列表中"}), 400

    model_supports_thinking = _supports_thinking(model_id)
    requested_enable_thinking = _parse_optional_bool(data.get("enable_thinking"))
    enable_thinking = bool(LLM_THINKING_DEFAULT_ENABLED)
    if requested_enable_thinking is not None:
        enable_thinking = requested_enable_thinking
    if not model_supports_thinking:
        enable_thinking = False
    thinking_budget, thinking_budget_level, thinking_budget_label = _resolve_thinking_budget(
        data.get("thinking_budget_level"),
        data.get("thinking_budget"),
    )

    attachment_parts = []
    attachment_stats = {"received": 0, "parsed": 0, "failed": 0}
    for file in _collect_uploaded_files(request.files):
        if file and file.filename:
            attachment_stats["received"] += 1
            parsed = parse_uploaded_attachment(file)
            if parsed:
                attachment_parts.append(parsed)
                if _is_attachment_parse_failure(parsed):
                    attachment_stats["failed"] += 1
                else:
                    attachment_stats["parsed"] += 1
            else:
                attachment_stats["failed"] += 1
    attachment_text = "\n\n".join(attachment_parts)
    language_style = data.get("language_style", "严谨学术")
    if language_style == "自定义":
        custom_style = data.get("custom_language_style", "").strip()
        language_style = custom_style or "自定义"

    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "status": "running",
        "cancel_requested": False,
        "progress": [],
        "result": None,
        "input": {
            "model_id": model_id,
            "enable_thinking": enable_thinking,
            "thinking_budget_level": thinking_budget_level,
            "thinking_budget": thinking_budget,
            "subject": data.get("subject", ""),
            "grade": data.get("grade", ""),
            "teaching_goals": data.get("teaching_goals", ""),
            "student_profile": data.get("student_profile", ""),
            "difficulty_analysis": data.get("difficulty_analysis", ""),
            "language_style": language_style,
            "attachment": attachment_text,
        },
    }

    tasks[task_id]["progress"].append(
        "[系统] 当前模型 ID：%s" % (model_id or "未指定")
    )

    if attachment_stats["received"] > 0:
        tasks[task_id]["progress"].append(
            "[系统] 附件上传统计：共 %d 个，成功解析 %d 个，失败 %d 个"
            % (attachment_stats["received"], attachment_stats["parsed"], attachment_stats["failed"])
        )
    else:
        tasks[task_id]["progress"].append("[系统] 未检测到附件，按表单输入继续生成")

    if model_supports_thinking:
        tasks[task_id]["progress"].append(
            "[系统] Think 模式：%s（思维链长度=%s，思维链长度=%d）"
            % (
                "开启" if enable_thinking else "关闭",
                thinking_budget_label or "未指定",
                thinking_budget,
            )
        )
    else:
        tasks[task_id]["progress"].append("[系统] 当前模型不支持 Think 参数，已自动忽略")

    app.logger.info(
        "[教学地图] task=%s model=%s supports_thinking=%s enable_thinking=%s thinking_budget_level=%s thinking_budget=%d attachment_received=%d attachment_parsed=%d attachment_failed=%d",
        task_id,
        model_id,
        model_supports_thinking,
        enable_thinking,
        thinking_budget_level,
        thinking_budget,
        attachment_stats["received"],
        attachment_stats["parsed"],
        attachment_stats["failed"],
    )

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

            if task["status"] in ("done", "error", "cancelled"):
                if task["status"] == "done":
                    event_type = "done"
                elif task["status"] == "cancelled":
                    event_type = "cancelled"
                else:
                    event_type = "error"
                payload = {
                    "type": event_type,
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
    if task["status"] == "cancelled":
        return jsonify({"status": "cancelled", "message": task.get("error_message", "")})
    if task["status"] == "error":
        return jsonify({"status": "error", "message": task.get("error_message", "")}), 500
    return jsonify({"status": "done", "result": task["result"]})


@app.route("/api/stop/<task_id>", methods=["POST"])
def stop_task(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    if task.get("status") in ("done", "error", "cancelled"):
        return jsonify({"ok": True, "status": task.get("status")})

    task["cancel_requested"] = True
    task["status"] = "cancelled"
    task["error_message"] = "任务已强制停止"
    task["progress"].append("[系统] 已收到强制停止请求，任务已标记为停止")
    return jsonify({"ok": True, "status": "cancelled"})


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
    "main_question_check": "主干问题综合校验Agent",
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
    "mark_variant_done": "系统-变式流水线完成",
    "mark_scaffold_done": "系统-支架流水线完成",
    "aggregate_sub_pipelines": "系统-变式/支架流水线汇合",
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
        "learning_analysis": ["model_id", "enable_thinking", "thinking_budget_level", "thinking_budget", "subject", "grade", "teaching_goals", "student_profile", "difficulty_analysis", "language_style", "attachment"],
        "teaching_logic_design": ["model_id", "enable_thinking", "thinking_budget_level", "thinking_budget", "subject", "grade", "teaching_goals", "analysis_result"],
        "main_question_chain": ["model_id", "enable_thinking", "thinking_budget_level", "thinking_budget", "subject", "grade", "teaching_goals", "student_profile", "difficulty_analysis", "language_style", "attachment", "map_construction_logic", "main_retry_count", "validation_results"],
        "main_question_check": ["subject", "grade", "teaching_goals", "analysis_result", "map_construction_logic", "main_questions", "attachment"],
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
            value = accumulated[f]
            if f == "attachment" and isinstance(value, str):
                preview[f] = _truncate_text(value, 1200)
            else:
                preview[f] = value

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
        selected_model_id = task.get("input", {}).get("model_id")
        thinking_options = {
            "enable_thinking": bool(task.get("input", {}).get("enable_thinking", False)),
            "thinking_budget": _normalize_thinking_budget(task.get("input", {}).get("thinking_budget")),
        }
        initial_state = {
            **task["input"],
            "main_retry_count": 0,
            "variant_retry_count": 0,
            "scaffold_retry_count": 0,
            "main_validation_feedback": [],
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

        with use_generator_model(selected_model_id, thinking_options=thinking_options):
            for state_snapshot in graph.stream(initial_state, config=stream_config):
                if task.get("cancel_requested"):
                    raise RuntimeError("__MAT_TASK_CANCELLED__")
                for node_name, node_output in state_snapshot.items():
                    if task.get("cancel_requested"):
                        raise RuntimeError("__MAT_TASK_CANCELLED__")
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

        if task.get("cancel_requested") or task.get("status") == "cancelled":
            raise RuntimeError("__MAT_TASK_CANCELLED__")

        task["result"] = accumulated.get("teaching_map", {"nodes": [], "edges": []})
        _save_to_db(task_id, task["input"], task["result"])
        task["status"] = "done"
        task["progress"].append("[系统] 教学地图生成完成！")

    except Exception as e:
        if str(e) == "__MAT_TASK_CANCELLED__":
            task["status"] = "cancelled"
            if not task.get("error_message"):
                task["error_message"] = "任务已强制停止"
            if not task.get("progress") or task["progress"][-1] != "[系统] 任务已强制停止":
                task["progress"].append("[系统] 任务已强制停止")
            return
        task["status"] = "error"
        task["error_message"] = str(e)
        task["progress"].append("[错误] %s" % str(e))
        print("[ERROR] Workflow failed: %s" % traceback.format_exc())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
