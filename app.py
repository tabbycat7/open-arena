import uuid
import random
import json
import os
import sys
import time
import threading
import traceback
from datetime import datetime
from typing import Dict, List, Optional

import pymysql
from flask import Flask, render_template, jsonify, request, abort, redirect, Response, stream_with_context, make_response

from flask_sqlalchemy import SQLAlchemy

import config
from topics import get_all_topics, get_topic_by_id
from debate_llm_api import enhance_argument, refute_argument
from lesson_fields import get_prompt_fields, get_rating_dimensions, build_prompt, PROMPT_TEMPLATE
from lesson_llm_api import generate_lesson_plan

# 将 multi_agent_teaching 目录加入 sys.path 以便导入其 agents 包
_mat_dir = os.path.join(os.path.dirname(__file__), "multi_agent_teaching")
if _mat_dir not in sys.path:
    sys.path.insert(0, _mat_dir)

from agents.graph import build_graph  # noqa: E402

app = Flask(__name__)

# ===================== 从 config 加载配置 =====================
app.config["SECRET_KEY"] = config.SECRET_KEY
app.config["SQLALCHEMY_DATABASE_URI"] = config.SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = config.SQLALCHEMY_TRACK_MODIFICATIONS
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = config.SQLALCHEMY_ENGINE_OPTIONS
app.config["JSON_AS_ASCII"] = False

db = SQLAlchemy(app)


VISITOR_COOKIE_NAME = "open_arena_visitor_id"


def _get_or_create_visitor_id() -> str:
    """获取当前访客 ID；若不存在则生成新的 UUID。"""
    visitor_id = request.cookies.get(VISITOR_COOKIE_NAME, "").strip()
    if visitor_id:
        return visitor_id
    return str(uuid.uuid4())


def _set_visitor_cookie(resp: Response, visitor_id: str) -> Response:
    """将访客 ID 写入 Cookie，供后续请求做轻量隔离。"""
    if request.cookies.get(VISITOR_COOKIE_NAME) != visitor_id:
        resp.set_cookie(
            VISITOR_COOKIE_NAME,
            visitor_id,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="Lax",
        )
    return resp


def _assert_session_owner(session_id: str, visitor_id: str, allow_auto_bind: bool = False) -> None:
    """校验会话归属；未命中归属时可按需自动绑定到当前访客。"""
    owner = DebateSessionOwner.query.filter_by(session_id=session_id).first()
    if owner is None:
        if allow_auto_bind:
            db.session.add(DebateSessionOwner(session_id=session_id, visitor_id=visitor_id))
            db.session.commit()
            return
        abort(404)
    if owner.visitor_id != visitor_id:
        abort(404)


def _assert_lesson_session_owner(session_id: str, visitor_id: str, allow_auto_bind: bool = False) -> None:
    """校验教案会话归属；未命中归属时可按需自动绑定到当前访客。"""
    owner = LessonSessionOwner.query.filter_by(session_id=session_id).first()
    if owner is None:
        if allow_auto_bind:
            db.session.add(LessonSessionOwner(session_id=session_id, visitor_id=visitor_id))
            db.session.commit()
            return
        abort(404)
    if owner.visitor_id != visitor_id:
        abort(404)



# ===================== 数据库模型（仅辩论过程数据） =====================
class DebateSession(db.Model):
    """辩论会话表 —— 记录一次完整辩论的元信息"""

    __tablename__ = "debate_sessions"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(36), unique=True, nullable=False, comment="会话UUID")
    topic_id = db.Column(db.String(20), nullable=False, comment="辩题编号，对应 topics.py 中的 topic_id")
    teacher_name = db.Column(db.String(100), comment="教师姓名")
    chosen_side = db.Column(db.String(10), nullable=False, comment="教师选择的立场: side_a / side_b")
    refute_model_name = db.Column(db.String(100), comment="本次会话锁定的反驳模型名称")
    current_round = db.Column(db.Integer, default=0, comment="当前轮次")
    stance_changed = db.Column(db.Boolean, nullable=True, comment="教师立场是否改变（人工标注）")
    annotation_note = db.Column(db.Text, comment="标注备注")
    status = db.Column(
        db.String(20),
        default="pending",
        comment="会话状态: pending/debating/annotated",
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    rounds = db.relationship("DebateRound", backref="session", lazy="dynamic",
                             order_by="DebateRound.round_number")


class DebateRound(db.Model):
    """辩论轮次表 —— 记录每一轮对话的完整数据"""

    __tablename__ = "debate_rounds"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(36), db.ForeignKey("debate_sessions.session_id"), nullable=False)
    round_number = db.Column(db.Integer, nullable=False, comment="轮次编号，从1开始")
    teacher_argument = db.Column(db.Text, nullable=False, comment="教师本轮原始观点")
    enhanced_argument_raw = db.Column(db.Text, comment="加持模型原始润色结果（AI生成）")
    enhanced_argument = db.Column(db.Text, comment="最终用于反驳的加持观点（可能经用户修改）")
    rebuttal_argument = db.Column(db.Text, comment="反驳模型的反驳内容")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DebateSessionOwner(db.Model):
    """辩论会话归属表 —— 轻量按访客隔离历史记录"""

    __tablename__ = "debate_session_owners"
    session_id = db.Column(
        db.String(36),
        db.ForeignKey("debate_sessions.session_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    visitor_id = db.Column(db.String(36), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ===================== 教案竞技场数据库模型 =====================
class LessonSession(db.Model):
    """教案竞技场会话表"""                                                                                                                                                                                                                  
    __tablename__ = "lesson_sessions"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(36), unique=True, nullable=False)
    teacher_name = db.Column(db.String(100), comment="教师姓名")
    prompt_text = db.Column(db.Text, nullable=False, comment="完整提示词")
    form_data = db.Column(db.Text, comment="表单原始数据 JSON")
    model_a_name = db.Column(db.String(100), nullable=False)
    model_b_name = db.Column(db.String(100), nullable=False)
    model_a_response = db.Column(db.Text, comment="模型A的回答")
    model_b_response = db.Column(db.Text, comment="模型B的回答")                                                                                                                                                                                                                                                                                                                                                                                                                
    winner = db.Column(db.String(10), comment="胜者: model_a / model_b / tie")
    rating_executable_a = db.Column(db.Integer, comment="模型A可执行性评分1-5")
    rating_student_fit_a = db.Column(db.Integer, comment="模型A学情匹配评分1-5")
    rating_practical_a = db.Column(db.Integer, comment="模型A扎实有用评分1-5")
    rating_local_integration_a = db.Column(db.Integer, comment="模型A本土融合评分1-5")                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              
    rating_tech_usage_a = db.Column(db.Integer, comment="模型A技术善用评分1-5")
    rating_executable_b = db.Column(db.Integer, comment="模型B可执行性评分1-5")
    rating_student_fit_b = db.Column(db.Integer, comment="模型B学情匹配评分1-5")
    rating_practical_b = db.Column(db.Integer, comment="模型B扎实有用评分1-5")
    rating_local_integration_b = db.Column(db.Integer, comment="模型B本土融合评分1-5")
    rating_tech_usage_b = db.Column(db.Integer, comment="模型B技术善用评分1-5")
    current_round = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default="generating", comment="generating/voted/completed")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    chat_rounds = db.relationship("LessonChatRound", backref="session", lazy="dynamic",
                                  order_by="LessonChatRound.round_number")


class LessonChatRound(db.Model):
    """教案竞技场多轮对话表"""
    __tablename__ = "lesson_chat_rounds"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(36), db.ForeignKey("lesson_sessions.session_id"), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)
    user_message = db.Column(db.Text, nullable=False, comment="用户追问内容")
    model_a_response = db.Column(db.Text, comment="模型A回答")
    model_b_response = db.Column(db.Text, comment="模型B回答")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class LessonSessionOwner(db.Model):
    """教案会话归属表 —— 轻量按访客隔离历史记录"""

    __tablename__ = "lesson_session_owners"
    session_id = db.Column(
        db.String(36),
        db.ForeignKey("lesson_sessions.session_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    visitor_id = db.Column(db.String(36), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ===================== 首页应用列表 =====================
AI_APPS = [
    {
        "id": "Q001",
        "title": "教育观辩论场",
        "description": "将教育观结合生活场景改造为辩题，通过「加持」与「反驳」双模型辅助教师辩论，测评教师教育观。",
        "icon": "debate",
        "tag": "教育测评",
        "tag_type": "primary",
        "url": "/app/debate",
        "status": "active",
    },
    {
        "id": "Q002",
        "title": "教案设计竞技场",
        "description": "填写教学信息，两个大模型同时生成教案，对比评估哪个更好，支持多轮追问与多维度评分。",
        "icon": "lesson",
        "tag": "教案设计",
        "tag_type": "success",
        "url": "/app/lesson-arena",
        "status": "active",
    },
    {
        "id": "Q003",
        "title": "教学导航仪",
        "description": "基于 LangGraph 的多智能体协作应用，自动生成结构化教学地图，支持过程追踪与历史回溯。",
        "icon": "multi_agent",
        "tag": "多智能体",
        "tag_type": "warning",
        "url": "/app/multi-agent-teaching",
        "status": "active",
    },
    {
        "id": "Q004",
        "title": "AI 智能翻译",
        "description": "支持 100+ 语言互译，结合上下文理解，提供更自然流畅的翻译结果。",
        "icon": "translate",
        "tag": "语言处理",
        "tag_type": "primary",
        "url": "/app/translate",
        "status": "coming_soon",
    },
    {
        "id": "Q005",
        "title": "AI 代码助手",
        "description": "智能代码补全、代码审查、Bug 修复与代码解释，提升开发效率。",
        "icon": "code",
        "tag": "开发工具",
        "tag_type": "danger",
        "url": "/app/code-assistant",
        "status": "coming_soon",
    },
    {
        "id": "Q006",
        "title": "AI 数据分析",
        "description": "上传数据文件，AI 自动完成数据清洗、统计分析并生成可视化报告。",
        "icon": "chart",
        "tag": "数据处理",
        "tag_type": "success",
        "url": "/app/data-analysis",
        "status": "coming_soon",
    },
]


# ===================== 辅助函数 =====================
def _build_history(rounds_list):
    """
    将历史轮次构建为对话历史列表，供大模型使用。
    返回格式: [{"round": 1, "teacher": "...", "enhanced": "...", "rebuttal": "..."}, ...]
    """
    history = []
    for r in rounds_list:
        entry = {
            "round": r.round_number,
            "teacher": r.teacher_argument,
        }
        if r.enhanced_argument:
            entry["enhanced"] = r.enhanced_argument
        if r.rebuttal_argument:
            entry["rebuttal"] = r.rebuttal_argument
        history.append(entry)
    return history


def _pick_refute_model():
    """从反驳模型列表中随机选取一个模型"""
    if config.REFUTE_MODEL_NAMES:
        return random.choice(config.REFUTE_MODEL_NAMES)
    return config.ENHANCE_MODEL_NAME


# ===================== 页面路由 =====================
@app.route("/")
def index():
    return render_template("index.html", apps=AI_APPS)


@app.route("/app/debate")
def debate_home():
    """辩论平台首页 —— 展示辩题列表（从 topics.py 读取）"""
    visitor_id = _get_or_create_visitor_id()
    topics = get_all_topics()
    # 每次进入/刷新辩题页时随机打乱顺序
    if topics:
        topics = random.sample(topics, len(topics))
    resp = make_response(render_template("debate.html", topics=topics))
    return _set_visitor_cookie(resp, visitor_id)


@app.route("/app/debate/random")
def debate_random_topic():
    """随机抽取一个辩题并跳转到该辩题页"""
    topics = get_all_topics()
    if not topics:
        return redirect("/app/debate")
    picked = random.choice(topics)
    return redirect(f"/app/debate/{picked['topic_id']}")


@app.route("/app/multi-agent-teaching")
def multi_agent_teaching_redirect():
    return redirect("/app/multi-agent-teaching/")


@app.route("/app/multi-agent-teaching/")
def multi_agent_teaching_page():
    """多智能体教学地图生成页面"""
    return render_template("multi_agent_teaching.html")


@app.route("/app/debate/history")
def debate_history_page():
    """历史辩论记录列表页"""
    visitor_id = _get_or_create_visitor_id()
    resp = make_response(render_template("debate_history.html"))
    return _set_visitor_cookie(resp, visitor_id)


@app.route("/app/debate/history/<session_id>")
def debate_history_detail_page(session_id):
    """查看某次辩论的详细记录"""
    visitor_id = _get_or_create_visitor_id()
    _assert_session_owner(session_id, visitor_id, allow_auto_bind=True)
    session = DebateSession.query.filter_by(session_id=session_id).first_or_404()
    topic = get_topic_by_id(session.topic_id)
    if not topic:
        abort(404)
    resp = make_response(render_template("debate_history_detail.html", session=session, topic=topic))
    return _set_visitor_cookie(resp, visitor_id)


@app.route("/app/debate/<topic_id>")
def debate_session_page(topic_id):
    """进入某个辩题的辩论页面"""
    visitor_id = _get_or_create_visitor_id()
    topic = get_topic_by_id(topic_id)
    if not topic:
        abort(404)
    resp = make_response(render_template("debate_session.html", topic=topic))
    return _set_visitor_cookie(resp, visitor_id)


# ===================== API 接口 =====================

# ---------- 通用 API ----------
@app.route("/api/apps")
def get_apps():
    return jsonify(AI_APPS)


# ---------- 辩题 API（只读，数据来自 topics.py） ----------
@app.route("/api/debate/topics", methods=["GET"])
def api_get_topics():
    """获取所有辩题"""
    topics = get_all_topics()
    return jsonify({"code": 0, "data": topics})


@app.route("/api/debate/topics/<topic_id>", methods=["GET"])
def api_get_topic(topic_id):
    """获取单个辩题"""
    topic = get_topic_by_id(topic_id)
    if not topic:
        return jsonify({"code": 1, "msg": "辩题不存在"}), 404
    return jsonify({"code": 0, "data": topic})


# ---------- 辩论会话 API ----------
@app.route("/api/debate/sessions", methods=["POST"])
def api_create_session():
    """
    创建辩论会话 —— 教师选择立场并提交第一轮观点
    请求体:
    {
        "topic_id": "P001",
        "teacher_name": "张老师",
        "chosen_side": "side_a",
        "teacher_argument": "我认为……"
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"code": 1, "msg": "请求体不能为空"}), 400

    required = ["topic_id", "chosen_side", "teacher_argument"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"code": 1, "msg": f"缺少必填字段: {', '.join(missing)}"}), 400

    topic = get_topic_by_id(data["topic_id"])
    if not topic:
        return jsonify({"code": 1, "msg": "辩题不存在"}), 404

    # 随机选取反驳模型并锁定到本次会话
    refute_model = _pick_refute_model()

    visitor_id = _get_or_create_visitor_id()

    session_id = str(uuid.uuid4())
    session = DebateSession(
        session_id=session_id,
        topic_id=data["topic_id"],
        teacher_name=data.get("teacher_name", ""),
        chosen_side=data["chosen_side"],
        refute_model_name=refute_model,
        current_round=1,
        status="debating",
    )
    db.session.add(session)
    db.session.add(DebateSessionOwner(session_id=session_id, visitor_id=visitor_id))

    # 创建第一轮
    round1 = DebateRound(
        session_id=session_id,
        round_number=1,
        teacher_argument=data["teacher_argument"],
    )
    db.session.add(round1)
    db.session.commit()

    resp = jsonify({
        "code": 0,
        "msg": "辩论会话创建成功",
        "data": {
            "session_id": session_id,
            "refute_model": refute_model,
            "round_number": 1,
        },
    })
    return _set_visitor_cookie(resp, visitor_id)


@app.route("/api/debate/sessions/<session_id>/enhance", methods=["POST"])
def api_enhance_argument(session_id):
    """加持模型 API —— 润色当前轮次的教师观点（含历史上下文）"""
    visitor_id = _get_or_create_visitor_id()
    _assert_session_owner(session_id, visitor_id, allow_auto_bind=True)
    session = DebateSession.query.filter_by(session_id=session_id).first_or_404()

    topic = get_topic_by_id(session.topic_id)
    if not topic:
        return jsonify({"code": 1, "msg": "辩题数据异常"}), 500

    # 获取当前轮次
    current_round = DebateRound.query.filter_by(
        session_id=session_id, round_number=session.current_round
    ).first()
    if not current_round or not current_round.teacher_argument:
        return jsonify({"code": 1, "msg": "教师尚未提交观点"}), 400

    # 允许重试：如果之前加持失败或用户想重新生成，清空旧数据重新调用
    chosen_label = topic["side_a"] if session.chosen_side == "side_a" else topic["side_b"]

    # 构建历史对话
    all_rounds = DebateRound.query.filter_by(session_id=session_id).order_by(
        DebateRound.round_number
    ).all()
    history = _build_history(all_rounds)

    try:
        enhanced = enhance_argument(
            topic_title=topic["title"],
            chosen_side_label=chosen_label,
            teacher_argument=current_round.teacher_argument,
            history=history,
        )
    except Exception as e:
        app.logger.error(f"加持模型调用失败: {e}")
        return jsonify({"code": 1, "msg": f"加持模型调用失败: {str(e)}"}), 500

    current_round.enhanced_argument_raw = enhanced
    current_round.enhanced_argument = enhanced
    session.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "code": 0,
        "data": {
            "session_id": session_id,
            "round_number": session.current_round,
            "enhanced_argument": enhanced,
        },
    })


@app.route("/api/debate/sessions/<session_id>/update-enhanced", methods=["POST"])
def api_update_enhanced(session_id):
    """
    用户修改加持后的观点 —— 在反驳之前允许用户编辑润色内容
    请求体:
    {
        "enhanced_argument": "修改后的观点内容"
    }
    """
    visitor_id = _get_or_create_visitor_id()
    _assert_session_owner(session_id, visitor_id, allow_auto_bind=True)
    session = DebateSession.query.filter_by(session_id=session_id).first_or_404()

    data = request.get_json()
    if not data or "enhanced_argument" not in data:
        return jsonify({"code": 1, "msg": "请提供 enhanced_argument 字段"}), 400

    current_round = DebateRound.query.filter_by(
        session_id=session_id, round_number=session.current_round
    ).first()
    if not current_round:
        return jsonify({"code": 1, "msg": "当前轮次不存在"}), 400

    if current_round.rebuttal_argument:
        return jsonify({"code": 1, "msg": "本轮已完成反驳，无法修改"}), 400

    current_round.enhanced_argument = data["enhanced_argument"].strip()
    session.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "code": 0,
        "msg": "观点已更新",
        "data": {
            "session_id": session_id,
            "round_number": session.current_round,
            "enhanced_argument": current_round.enhanced_argument,
        },
    })


@app.route("/api/debate/sessions/<session_id>/rebut", methods=["POST"])
def api_rebut_argument(session_id):
    """反驳模型 API —— 反驳当前轮次加持后的观点（含历史上下文，使用锁定的模型）"""
    visitor_id = _get_or_create_visitor_id()
    _assert_session_owner(session_id, visitor_id, allow_auto_bind=True)
    session = DebateSession.query.filter_by(session_id=session_id).first_or_404()

    topic = get_topic_by_id(session.topic_id)
    if not topic:
        return jsonify({"code": 1, "msg": "辩题数据异常"}), 500

    current_round = DebateRound.query.filter_by(
        session_id=session_id, round_number=session.current_round
    ).first()
    if not current_round or not current_round.enhanced_argument:
        return jsonify({"code": 1, "msg": "请先完成观点加持"}), 400

    # 允许重试：如果之前反驳失败或用户想重新生成，清空旧数据重新调用
    opposite_label = topic["side_b"] if session.chosen_side == "side_a" else topic["side_a"]

    # 构建历史对话
    all_rounds = DebateRound.query.filter_by(session_id=session_id).order_by(
        DebateRound.round_number
    ).all()
    history = _build_history(all_rounds)

    try:
        rebuttal = refute_argument(
            topic_title=topic["title"],
            enhanced_argument=current_round.enhanced_argument,
            opposite_side_label=opposite_label,
            history=history,
            model_name=session.refute_model_name,
        )
    except Exception as e:
        app.logger.error(f"反驳模型调用失败: {e}")
        return jsonify({"code": 1, "msg": f"反驳模型调用失败: {str(e)}"}), 500

    current_round.rebuttal_argument = rebuttal
    session.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "code": 0,
        "data": {
            "session_id": session_id,
            "round_number": session.current_round,
            "rebuttal_argument": rebuttal,
        },
    })


@app.route("/api/debate/sessions/<session_id>/next-round", methods=["POST"])
def api_next_round(session_id):
    """
    提交新一轮辩论观点（教师针对上一轮反驳进行再辩论）
    请求体:
    {
        "teacher_argument": "针对你的反驳，我认为……"
    }
    """
    visitor_id = _get_or_create_visitor_id()
    _assert_session_owner(session_id, visitor_id, allow_auto_bind=True)
    session = DebateSession.query.filter_by(session_id=session_id).first_or_404()

    if session.status != "debating":
        return jsonify({"code": 1, "msg": "会话已结束"}), 400

    data = request.get_json()
    if not data or "teacher_argument" not in data:
        return jsonify({"code": 1, "msg": "请提供 teacher_argument 字段"}), 400

    # 检查上一轮是否已完成反驳
    prev_round = DebateRound.query.filter_by(
        session_id=session_id, round_number=session.current_round
    ).first()
    if not prev_round or not prev_round.rebuttal_argument:
        return jsonify({"code": 1, "msg": "上一轮尚未完成"}), 400

    # 创建新一轮
    new_round_number = session.current_round + 1
    new_round = DebateRound(
        session_id=session_id,
        round_number=new_round_number,
        teacher_argument=data["teacher_argument"],
    )
    db.session.add(new_round)

    session.current_round = new_round_number
    session.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "code": 0,
        "data": {
            "session_id": session_id,
            "round_number": new_round_number,
        },
    })


@app.route("/api/debate/sessions/<session_id>/annotate", methods=["POST"])
def api_annotate_session(session_id):
    """
    人工标注 API —— 标注教师立场是否改变
    请求体:
    {
        "stance_changed": true/false,
        "annotation_note": "备注信息"
    }
    """
    visitor_id = _get_or_create_visitor_id()
    _assert_session_owner(session_id, visitor_id, allow_auto_bind=True)
    session = DebateSession.query.filter_by(session_id=session_id).first_or_404()
    data = request.get_json()

    if data is None or "stance_changed" not in data:
        return jsonify({"code": 1, "msg": "请提供 stance_changed 字段"}), 400

    session.stance_changed = data["stance_changed"]
    session.annotation_note = data.get("annotation_note", "")
    session.status = "annotated"
    session.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"code": 0, "msg": "标注完成"})


@app.route("/api/debate/sessions/<session_id>", methods=["GET"])
def api_get_session(session_id):
    """获取单个辩论会话详情（含所有轮次）"""
    visitor_id = _get_or_create_visitor_id()
    _assert_session_owner(session_id, visitor_id, allow_auto_bind=True)
    session = DebateSession.query.filter_by(session_id=session_id).first_or_404()
    topic = get_topic_by_id(session.topic_id)

    rounds_data = []
    for r in session.rounds.all():
        rounds_data.append({
            "round_number": r.round_number,
            "teacher_argument": r.teacher_argument,
            "enhanced_argument_raw": r.enhanced_argument_raw,
            "enhanced_argument": r.enhanced_argument,
            "rebuttal_argument": r.rebuttal_argument,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return jsonify({
        "code": 0,
        "data": {
            "session_id": session.session_id,
            "topic_id": session.topic_id,
            "topic": topic,
            "teacher_name": session.teacher_name,
            "chosen_side": session.chosen_side,
            "refute_model_name": session.refute_model_name,
            "current_round": session.current_round,
            "rounds": rounds_data,
            "stance_changed": session.stance_changed,
            "annotation_note": session.annotation_note,
            "status": session.status,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        },
    })


@app.route("/api/debate/sessions", methods=["GET"])
def api_list_sessions():
    """获取辩论会话列表（支持按辩题筛选）"""
    visitor_id = _get_or_create_visitor_id()
    topic_id = request.args.get("topic_id")
    owner_query = DebateSessionOwner.query.filter_by(visitor_id=visitor_id)
    owned_session_ids = [o.session_id for o in owner_query.all()]
    if not owned_session_ids:
        return jsonify({"code": 0, "data": []})

    query = DebateSession.query.filter(DebateSession.session_id.in_(owned_session_ids))
    if topic_id:
        query = query.filter_by(topic_id=topic_id)
    sessions = query.order_by(DebateSession.created_at.desc()).all()
    result = []
    for s in sessions:
        topic = get_topic_by_id(s.topic_id)
        result.append({
            "session_id": s.session_id,
            "topic_id": s.topic_id,
            "topic_title": topic["title"] if topic else "未知辩题",
            "teacher_name": s.teacher_name,
            "chosen_side": s.chosen_side,
            "refute_model_name": s.refute_model_name,
            "current_round": s.current_round,
            "status": s.status,
            "stance_changed": s.stance_changed,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })
    return jsonify({"code": 0, "data": result})


# ===================== 教案设计竞技场 - 页面路由 =====================
@app.route("/app/lesson-arena")
def lesson_arena_home():
    """教案竞技场首页 —— 填写提示词模板表单"""
    visitor_id = _get_or_create_visitor_id()
    fields = get_prompt_fields()
    resp = make_response(render_template("lesson_arena.html", fields=fields, prompt_template=PROMPT_TEMPLATE))
    return _set_visitor_cookie(resp, visitor_id)


@app.route("/app/lesson-arena/history")
def lesson_arena_history_page():
    """教案竞技场历史记录页"""
    visitor_id = _get_or_create_visitor_id()
    resp = make_response(render_template("lesson_history.html"))
    return _set_visitor_cookie(resp, visitor_id)


@app.route("/app/lesson-arena/session/<session_id>")
def lesson_arena_session_page(session_id):
    """教案竞技场会话页 —— 对比两模型回答、投票、评分、多轮对话"""
    visitor_id = _get_or_create_visitor_id()
    _assert_lesson_session_owner(session_id, visitor_id, allow_auto_bind=True)
    session = LessonSession.query.filter_by(session_id=session_id).first_or_404()
    dimensions = get_rating_dimensions()
    resp = make_response(render_template("lesson_session.html", session=session, dimensions=dimensions))
    return _set_visitor_cookie(resp, visitor_id)


# ===================== 教案设计竞技场 - API =====================
@app.route("/api/lesson/sessions", methods=["GET"])
def api_lesson_list_sessions():
    """获取教案竞技场会话列表（用于历史记录展示）"""
    visitor_id = _get_or_create_visitor_id()
    owner_query = LessonSessionOwner.query.filter_by(visitor_id=visitor_id)
    owned_session_ids = [o.session_id for o in owner_query.all()]
    if not owned_session_ids:
        resp = jsonify({"code": 0, "data": []})
        return _set_visitor_cookie(resp, visitor_id)

    sessions = LessonSession.query.filter(
        LessonSession.session_id.in_(owned_session_ids)
    ).order_by(LessonSession.created_at.desc()).all()

    result = []
    for s in sessions:
        lesson_focus = ""
        try:
            form_data = json.loads(s.form_data) if s.form_data else {}
            lesson_focus = (
                form_data.get("knowledge_point")
                or form_data.get("grade_subject")
                or form_data.get("teaching_stage")
                or ""
            )
        except Exception:
            lesson_focus = ""

        result.append({
            "session_id": s.session_id,
            "teacher_name": s.teacher_name or "匿名",
            "status": s.status,
            "winner": s.winner,
            "current_round": s.current_round,
            "model_a_name": s.model_a_name,
            "model_b_name": s.model_b_name,
            "lesson_focus": lesson_focus,
            "prompt_preview": (s.prompt_text or "")[:120],
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        })

    resp = jsonify({"code": 0, "data": result})
    return _set_visitor_cookie(resp, visitor_id)


@app.route("/api/lesson/sessions", methods=["POST"])
def api_lesson_create_session():
    """
    创建教案竞技场会话 —— 提交表单数据，随机抽取两个模型生成教案
    """
    data = request.get_json()
    if not data or "form_data" not in data:
        return jsonify({"code": 1, "msg": "请求体不能为空"}), 400

    form_data = data["form_data"]
    teacher_name = data.get("teacher_name", "")

    required_keys = [f["key"] for f in get_prompt_fields() if f["required"]]
    missing = [k for k in required_keys if not form_data.get(k, "").strip()]
    if missing:
        return jsonify({"code": 1, "msg": f"以下字段不能为空: {', '.join(missing)}"}), 400

    prompt_text = build_prompt(form_data)

    models = config.LESSON_MODEL_NAMES[:]
    if len(models) < 2:
        return jsonify({"code": 1, "msg": "模型列表不足2个，请检查配置"}), 500

    picked = random.sample(models, 2)
    model_a, model_b = picked[0], picked[1]
    visitor_id = _get_or_create_visitor_id()

    session_id = str(uuid.uuid4())
    lesson_session = LessonSession(
        session_id=session_id,
        teacher_name=teacher_name,
        prompt_text=prompt_text,
        form_data=json.dumps(form_data, ensure_ascii=False),
        model_a_name=model_a,
        model_b_name=model_b,
        status="generating",
    )
    db.session.add(lesson_session)
    db.session.add(LessonSessionOwner(session_id=session_id, visitor_id=visitor_id))
    db.session.commit()

    resp = jsonify({
        "code": 0,
        "data": {"session_id": session_id},
    })
    return _set_visitor_cookie(resp, visitor_id)


@app.route("/api/lesson/sessions/<session_id>/generate", methods=["POST"])
def api_lesson_generate(session_id):
    """调用两个模型并行生成教案（由前端在进入会话页后调用）"""
    visitor_id = _get_or_create_visitor_id()
    _assert_lesson_session_owner(session_id, visitor_id, allow_auto_bind=True)
    session = LessonSession.query.filter_by(session_id=session_id).first_or_404()

    if session.model_a_response and session.model_b_response:
        return jsonify({
            "code": 0,
            "data": {
                "model_a_response": session.model_a_response,
                "model_b_response": session.model_b_response,
            },
        })

    errors = []

    if not session.model_a_response:
        try:
            resp_a = generate_lesson_plan(
                prompt_text=session.prompt_text,
                model_name=session.model_a_name,
            )
            session.model_a_response = resp_a
        except Exception as e:
            app.logger.error(f"模型A({session.model_a_name})调用失败: {e}")
            errors.append(f"模型A调用失败: {str(e)}")

    if not session.model_b_response:
        try:
            resp_b = generate_lesson_plan(
                prompt_text=session.prompt_text,
                model_name=session.model_b_name,
            )
            session.model_b_response = resp_b
        except Exception as e:
            app.logger.error(f"模型B({session.model_b_name})调用失败: {e}")
            errors.append(f"模型B调用失败: {str(e)}")

    if not session.model_a_response and not session.model_b_response:
        return jsonify({"code": 1, "msg": "两个模型均调用失败: " + "; ".join(errors)}), 500

    session.status = "ready"
    session.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "code": 0,
        "data": {
            "model_a_response": session.model_a_response,
            "model_b_response": session.model_b_response,
            "errors": errors if errors else None,
        },
    })


@app.route("/api/lesson/sessions/<session_id>/vote", methods=["POST"])
def api_lesson_vote(session_id):
    """用户投票选择哪个模型更好"""
    visitor_id = _get_or_create_visitor_id()
    _assert_lesson_session_owner(session_id, visitor_id, allow_auto_bind=True)
    session = LessonSession.query.filter_by(session_id=session_id).first_or_404()
    data = request.get_json()

    if not data or "winner" not in data:
        return jsonify({"code": 1, "msg": "请提供 winner 字段"}), 400

    winner = data["winner"]
    if winner not in ("model_a", "model_b"):
        return jsonify({"code": 1, "msg": "winner 必须是 model_a / model_b"}), 400

    session.winner = winner
    session.status = "voted"
    session.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "code": 0,
        "msg": "投票成功",
        "data": {
            "model_a_name": session.model_a_name,
            "model_b_name": session.model_b_name,
            "winner": winner,
        },
    })


@app.route("/api/lesson/sessions/<session_id>/rate", methods=["POST"])
def api_lesson_rate(session_id):
    """
    多维度评分（5分李克特量表）
    请求体: { "ratings_a": {"executable":5,...}, "ratings_b": {"executable":3,...} }
    """
    visitor_id = _get_or_create_visitor_id()
    _assert_lesson_session_owner(session_id, visitor_id, allow_auto_bind=True)
    session = LessonSession.query.filter_by(session_id=session_id).first_or_404()
    data = request.get_json()

    if not data or "ratings_a" not in data or "ratings_b" not in data:
        return jsonify({"code": 1, "msg": "请提供 ratings_a 和 ratings_b"}), 400

    dim_keys = [d["key"] for d in get_rating_dimensions()]
    for key in dim_keys:
        val_a = data["ratings_a"].get(key)
        val_b = data["ratings_b"].get(key)
        if val_a is None or val_b is None:
            return jsonify({"code": 1, "msg": f"评分维度 {key} 不完整"}), 400
        if not (1 <= int(val_a) <= 5) or not (1 <= int(val_b) <= 5):
            return jsonify({"code": 1, "msg": f"评分必须在1-5之间"}), 400

    session.rating_executable_a = int(data["ratings_a"]["executable"])
    session.rating_student_fit_a = int(data["ratings_a"]["student_fit"])
    session.rating_practical_a = int(data["ratings_a"]["practical"])
    session.rating_local_integration_a = int(data["ratings_a"]["local_integration"])
    session.rating_tech_usage_a = int(data["ratings_a"]["tech_usage"])

    session.rating_executable_b = int(data["ratings_b"]["executable"])
    session.rating_student_fit_b = int(data["ratings_b"]["student_fit"])
    session.rating_practical_b = int(data["ratings_b"]["practical"])
    session.rating_local_integration_b = int(data["ratings_b"]["local_integration"])
    session.rating_tech_usage_b = int(data["ratings_b"]["tech_usage"])

    session.status = "completed"
    session.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"code": 0, "msg": "评分提交成功"})


@app.route("/api/lesson/sessions/<session_id>/chat", methods=["POST"])
def api_lesson_chat(session_id):
    """
    多轮对话 —— 用户追问，两个模型分别回答
    请求体: { "message": "请把导入环节改为游戏化方式" }
    """
    visitor_id = _get_or_create_visitor_id()
    _assert_lesson_session_owner(session_id, visitor_id, allow_auto_bind=True)
    session = LessonSession.query.filter_by(session_id=session_id).first_or_404()
    data = request.get_json()

    if not data or not data.get("message", "").strip():
        return jsonify({"code": 1, "msg": "请提供追问内容"}), 400

    user_message = data["message"].strip()

    # 构建历史对话
    history_a = [{"role": "user", "content": session.prompt_text}]
    if session.model_a_response:
        history_a.append({"role": "assistant", "content": session.model_a_response})

    history_b = [{"role": "user", "content": session.prompt_text}]
    if session.model_b_response:
        history_b.append({"role": "assistant", "content": session.model_b_response})

    for r in session.chat_rounds.order_by(LessonChatRound.round_number).all():
        history_a.append({"role": "user", "content": r.user_message})
        if r.model_a_response:
            history_a.append({"role": "assistant", "content": r.model_a_response})
        history_b.append({"role": "user", "content": r.user_message})
        if r.model_b_response:
            history_b.append({"role": "assistant", "content": r.model_b_response})

    new_round_number = session.current_round + 1
    resp_a_text = None
    resp_b_text = None
    errors = []

    try:
        resp_a_text = generate_lesson_plan(
            prompt_text=user_message,
            history=history_a,
            model_name=session.model_a_name,
        )
    except Exception as e:
        app.logger.error(f"多轮对话模型A调用失败: {e}")
        errors.append(f"模型A回复失败: {str(e)}")

    try:
        resp_b_text = generate_lesson_plan(
            prompt_text=user_message,
            history=history_b,
            model_name=session.model_b_name,
        )
    except Exception as e:
        app.logger.error(f"多轮对话模型B调用失败: {e}")
        errors.append(f"模型B回复失败: {str(e)}")

    chat_round = LessonChatRound(
        session_id=session_id,
        round_number=new_round_number,
        user_message=user_message,
        model_a_response=resp_a_text,
        model_b_response=resp_b_text,
    )
    db.session.add(chat_round)

    session.current_round = new_round_number
    session.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "code": 0,
        "data": {
            "round_number": new_round_number,
            "model_a_response": resp_a_text,
            "model_b_response": resp_b_text,
            "errors": errors if errors else None,
        },
    })


@app.route("/api/lesson/sessions/<session_id>", methods=["GET"])
def api_lesson_get_session(session_id):
    """获取教案竞技场会话详情"""
    visitor_id = _get_or_create_visitor_id()
    _assert_lesson_session_owner(session_id, visitor_id, allow_auto_bind=True)
    session = LessonSession.query.filter_by(session_id=session_id).first_or_404()

    chat_rounds = []
    for r in session.chat_rounds.order_by(LessonChatRound.round_number).all():
        chat_rounds.append({
            "round_number": r.round_number,
            "user_message": r.user_message,
            "model_a_response": r.model_a_response,
            "model_b_response": r.model_b_response,
        })

    return jsonify({
        "code": 0,
        "data": {
            "session_id": session.session_id,
            "teacher_name": session.teacher_name,
            "prompt_text": session.prompt_text,
            "form_data": json.loads(session.form_data) if session.form_data else None,
            "model_a_name": session.model_a_name,
            "model_b_name": session.model_b_name,
            "model_a_response": session.model_a_response,
            "model_b_response": session.model_b_response,
            "winner": session.winner,
            "status": session.status,
            "current_round": session.current_round,
            "chat_rounds": chat_rounds,
            "created_at": session.created_at.isoformat() if session.created_at else None,
        },
    })


# ===================== 自动创建数据库和表 =====================
def _ensure_database():
    """如果数据库不存在则自动创建，然后创建所有表"""
    import pymysql
    from urllib.parse import urlparse

    parsed = urlparse(config.SQLALCHEMY_DATABASE_URI)
    db_name = parsed.path.lstrip("/").split("?")[0]
    host = parsed.hostname or "localhost"
    port = parsed.port or 3306
    user = parsed.username or "root"
    password = parsed.password or ""

    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=password)
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                f"DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.close()
    except Exception as e:
        app.logger.warning(f"自动创建数据库失败（可忽略如果数据库已存在）: {e}")

    with app.app_context():
        db.create_all()


_ensure_database()


# ===================== 多智能体教学地图 - 内存任务存储 =====================
_mat_tasks: Dict[str, dict] = {}

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
    "aggregate_sub_pipelines": "系统-变式/支架流水线汇合",
    "map_integration": "教学地图整合Agent",
    "bump_main_retry": "系统-主干问题重试",
    "bump_variant_retry": "系统-变式问题重试",
    "bump_scaffold_retry": "系统-支架问题重试",
}


# ===================== 多智能体教学地图 - MySQL 直连辅助（独立库） =====================
def _mat_get_conn():
    from urllib.parse import urlparse
    parsed = urlparse(config.SQLALCHEMY_DATABASE_URI)
    return pymysql.connect(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 3306,
        user=parsed.username or "root",
        password=parsed.password or "",
        database=config.TEACHING_MAP_MYSQL_DB,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def _mat_init_db():
    from urllib.parse import urlparse
    parsed = urlparse(config.SQLALCHEMY_DATABASE_URI)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 3306
    user = parsed.username or "root"
    password = parsed.password or ""
    db_name = config.TEACHING_MAP_MYSQL_DB

    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=password, charset="utf8mb4")
    except pymysql.err.OperationalError as e:
        app.logger.warning(f"[教学地图] MySQL 连接失败: {e}")
        return

    with conn.cursor() as cur:
        cur.execute("CREATE DATABASE IF NOT EXISTS `%s` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci" % db_name)
    conn.commit()
    conn.close()

    conn = _mat_get_conn()
    with conn.cursor() as cur:
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
    conn.commit()
    conn.close()
    app.logger.info("[教学地图] 数据库初始化完成")


def _mat_save_to_db(task_id: str, inputs: dict, result: dict):
    conn = _mat_get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "REPLACE INTO history (id, subject, grade, teaching_goals, student_profile, language_style, result_json, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (task_id, inputs.get("subject", ""), inputs.get("grade", ""),
             inputs.get("teaching_goals", ""), inputs.get("student_profile", ""),
             inputs.get("language_style", ""),
             json.dumps(result, ensure_ascii=False),
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
    conn.commit()
    conn.close()


def _mat_save_agent_log(task_id: str, step_number: int, agent_name: str, output: dict):
    conn = _mat_get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO agent_logs (task_id, step_number, agent_name, output_json, created_at) VALUES (%s, %s, %s, %s, %s)",
            (task_id, step_number, agent_name,
             json.dumps(output, ensure_ascii=False, default=str),
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
    conn.commit()
    conn.close()


def _mat_get_agent_logs(task_id: str) -> List[dict]:
    conn = _mat_get_conn()
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


def _mat_get_history(limit: int = 50) -> List[dict]:
    conn = _mat_get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, subject, grade, teaching_goals, student_profile, language_style, created_at FROM history ORDER BY created_at DESC LIMIT %s",
            (limit,),
        )
        rows = cur.fetchall()
    conn.close()
    for r in rows:
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].strftime("%Y-%m-%d %H:%M:%S")
    return rows


def _mat_get_history_detail(record_id: str) -> Optional[dict]:
    conn = _mat_get_conn()
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


def _mat_truncate_text(text: str, limit: int = 140) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _mat_build_output_preview(output: dict) -> dict:
    return {k: v for k, v in output.items() if k != "progress_messages"}


def _mat_build_input_preview(node_name: str, accumulated: dict) -> dict:
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
        "map_integration": ["subject", "grade", "teaching_goals", "analysis_result", "main_questions", "variant_questions", "scaffold_questions"],
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
        preview["map_construction_logic"] = {"main_question_chain": map_logic.get("main_question_chain", [])}
    return preview


def _mat_run_workflow(task_id: str):
    task = _mat_tasks[task_id]
    try:
        graph = build_graph()
        initial_state = {
            **task["input"],
            "main_retry_count": 0,
            "variant_retry_count": 0,
            "scaffold_retry_count": 0,
            "main_checks_done": 0,
            "main_checks_expected": 3,
            "sub_pipelines_done": 0,
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
                    input_preview = _mat_build_input_preview(node_name, accumulated)
                    new_messages = node_output.get("progress_messages", [])
                    output_preview = _mat_build_output_preview(node_output)

                    progress_item = {
                        "message": new_messages[0] if new_messages else "%s 执行完成" % agent_display_name,
                        "agent": node_name,
                        "agent_display_name": agent_display_name,
                        "step_number": step_number,
                        "input_preview": input_preview,
                        "output_preview": output_preview,
                    }
                    task["progress"].append(progress_item)
                    for msg in new_messages[1:]:
                        task["progress"].append({**progress_item, "message": msg})

                    for key, value in node_output.items():
                        if key == "progress_messages":
                            continue
                        accumulated[key] = value

                    log_output = {k: v for k, v in node_output.items() if k != "progress_messages"}
                    try:
                        _mat_save_agent_log(task_id, step_number, agent_display_name, {
                            "input_preview": input_preview,
                            "output": log_output,
                        })
                    except Exception as log_err:
                        app.logger.warning(f"[教学地图] 保存日志失败: {log_err}")

        task["result"] = accumulated.get("teaching_map", {"nodes": [], "edges": []})
        _mat_save_to_db(task_id, task["input"], task["result"])
        task["status"] = "done"
        task["progress"].append("[系统] 教学地图生成完成！")

    except Exception as e:
        task["status"] = "error"
        task["error_message"] = str(e)
        task["progress"].append("[错误] %s" % str(e))
        app.logger.error(f"[教学地图] Workflow failed: {traceback.format_exc()}")


# ===================== 多智能体教学地图 - API 路由 =====================
@app.route("/api/mat/generate", methods=["POST"])
def mat_generate():
    """创建教学地图生成任务"""
    data = request.form
    attachment_text = ""
    if "attachment" in request.files:
        file = request.files["attachment"]
        if file.filename:
            attachment_text = file.read().decode("utf-8", errors="ignore")

    task_id = str(uuid.uuid4())
    _mat_tasks[task_id] = {
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

    thread = threading.Thread(target=_mat_run_workflow, args=(task_id,), daemon=True)
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/api/mat/stream/<task_id>")
def mat_stream(task_id):
    """SSE 实时推送教学地图生成进度"""
    from_idx = request.args.get("from", "0")
    try:
        start_sent = max(int(from_idx), 0)
    except ValueError:
        start_sent = 0

    def event_stream():
        if task_id not in _mat_tasks:
            yield "data: %s\n\n" % json.dumps({"type": "error", "message": "Task not found"}, ensure_ascii=False)
            return

        sent = start_sent
        while True:
            task = _mat_tasks[task_id]
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


@app.route("/api/mat/result/<task_id>")
def mat_get_result(task_id):
    """获取教学地图任务结果"""
    task = _mat_tasks.get(task_id)
    if not task:
        record = _mat_get_history_detail(task_id)
        if record:
            return jsonify({"status": "done", "result": record["result"]})
        return jsonify({"error": "Task not found"}), 404
    if task["status"] == "running":
        return jsonify({"status": "running", "progress": task["progress"]})
    if task["status"] == "error":
        return jsonify({"status": "error", "message": task.get("error_message", "")}), 500
    return jsonify({"status": "done", "result": task["result"]})


@app.route("/api/mat/history")
def mat_history_list():
    """教学地图历史列表"""
    return jsonify(_mat_get_history())


@app.route("/api/mat/history/<record_id>")
def mat_history_detail(record_id):
    """教学地图历史详情"""
    record = _mat_get_history_detail(record_id)
    if not record:
        return jsonify({"error": "Record not found"}), 404
    return jsonify(record)


@app.route("/api/mat/history/<record_id>", methods=["DELETE"])
def mat_history_delete(record_id):
    """删除教学地图历史记录"""
    conn = _mat_get_conn()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM history WHERE id = %s", (record_id,))
        cur.execute("DELETE FROM agent_logs WHERE task_id = %s", (record_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/mat/logs/<task_id>")
def mat_get_logs(task_id):
    """获取教学地图 Agent 日志"""
    logs = _mat_get_agent_logs(task_id)
    return jsonify(logs)


# ===================== 启动 =====================
try:
    _mat_init_db()
except Exception as _e:
    app.logger.warning(f"[教学地图] 数据库初始化失败: {_e}")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
