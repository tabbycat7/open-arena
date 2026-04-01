import uuid
import random
import json
from datetime import datetime
from flask import Flask, render_template, jsonify, request, abort
from flask_sqlalchemy import SQLAlchemy

import config
from topics import get_all_topics, get_topic_by_id
from llm_api import enhance_argument, refute_argument

app = Flask(__name__)

# ===================== 从 config 加载配置 =====================
app.config["SECRET_KEY"] = config.SECRET_KEY
app.config["SQLALCHEMY_DATABASE_URI"] = config.SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = config.SQLALCHEMY_TRACK_MODIFICATIONS
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = config.SQLALCHEMY_ENGINE_OPTIONS
app.config["JSON_AS_ASCII"] = False

db = SQLAlchemy(app)


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
    """辩论轮次表 —— 记录每一轮对话的内容"""

    __tablename__ = "debate_rounds"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(36), db.ForeignKey("debate_sessions.session_id"), nullable=False)
    round_number = db.Column(db.Integer, nullable=False, comment="轮次编号，从1开始")
    teacher_argument = db.Column(db.Text, nullable=False, comment="教师本轮观点")
    enhanced_argument = db.Column(db.Text, comment="加持模型润色后的观点")
    rebuttal_argument = db.Column(db.Text, comment="反驳模型的反驳内容")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ===================== 首页应用列表 =====================
AI_APPS = [
    {
        "id": "Q001",
        "title": "教育观测评平台",
        "description": "将教育观结合生活场景改造为辩题，通过「加持」与「反驳」双模型辅助教师辩论，测评教师教育观。",
        "icon": "debate",
        "tag": "教育测评",
        "tag_type": "primary",
        "url": "/app/debate",
        "status": "active",
    },
    {
        "id": "Q002",
        "title": "AI 图像分析",
        "description": "上传图片，AI 自动识别图像内容、场景描述，支持多种图像理解任务。",
        "icon": "image",
        "tag": "视觉理解",
        "tag_type": "success",
        "url": "/app/image-analysis",
        "status": "coming_soon",
    },
    {
        "id": "Q003",
        "title": "AI 语音转写",
        "description": "将语音文件或实时语音精准转换为文字，支持多语言识别与标点还原。",
        "icon": "audio",
        "tag": "语音处理",
        "tag_type": "warning",
        "url": "/app/speech-to-text",
        "status": "coming_soon",
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
    topics = get_all_topics()
    return render_template("debate.html", topics=topics)


@app.route("/app/debate/<topic_id>")
def debate_session_page(topic_id):
    """进入某个辩题的辩论页面"""
    topic = get_topic_by_id(topic_id)
    if not topic:
        abort(404)
    return render_template("debate_session.html", topic=topic)


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

    # 创建第一轮
    round1 = DebateRound(
        session_id=session_id,
        round_number=1,
        teacher_argument=data["teacher_argument"],
    )
    db.session.add(round1)
    db.session.commit()

    return jsonify({
        "code": 0,
        "msg": "辩论会话创建成功",
        "data": {
            "session_id": session_id,
            "refute_model": refute_model,
            "round_number": 1,
        },
    })


@app.route("/api/debate/sessions/<session_id>/enhance", methods=["POST"])
def api_enhance_argument(session_id):
    """加持模型 API —— 润色当前轮次的教师观点（含历史上下文）"""
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

    if current_round.enhanced_argument:
        return jsonify({"code": 1, "msg": "本轮已完成加持"}), 400

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
    session = DebateSession.query.filter_by(session_id=session_id).first_or_404()

    topic = get_topic_by_id(session.topic_id)
    if not topic:
        return jsonify({"code": 1, "msg": "辩题数据异常"}), 500

    current_round = DebateRound.query.filter_by(
        session_id=session_id, round_number=session.current_round
    ).first()
    if not current_round or not current_round.enhanced_argument:
        return jsonify({"code": 1, "msg": "请先完成观点加持"}), 400

    if current_round.rebuttal_argument:
        return jsonify({"code": 1, "msg": "本轮已完成反驳"}), 400

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
    session = DebateSession.query.filter_by(session_id=session_id).first_or_404()
    topic = get_topic_by_id(session.topic_id)

    rounds_data = []
    for r in session.rounds.all():
        rounds_data.append({
            "round_number": r.round_number,
            "teacher_argument": r.teacher_argument,
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
    topic_id = request.args.get("topic_id")
    query = DebateSession.query
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


# ===================== 启动 =====================
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
