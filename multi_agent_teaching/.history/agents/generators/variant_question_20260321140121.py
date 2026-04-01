"""Agent 2.1.3 — 变式问题生成Agent"""

import json
import os
import re
from agents.llm import get_llm

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "variant_question.txt")


def _format_validation_feedback(state: dict) -> str:
    """从验证结果中提取变式问题相关的反馈（来自 variant_alignment）"""
    feedback_parts = []

    for vr in state.get("validation_results", []):
        if vr.get("validator") != "variant_alignment":
            continue
        if vr.get("passed", True):
            continue

        total_score = vr.get("total_score", "?")
        overall = vr.get("overall_assessment", "")

        feedback_parts.append("=" * 50)
        feedback_parts.append("## 上一轮【变式问题检验】反馈（得分：%s/6）" % total_score)
        if overall:
            feedback_parts.append("总体评价：%s" % overall)

        feedback = vr.get("feedback", {})

        must_fix = feedback.get("must_fix", [])
        if must_fix:
            feedback_parts.append("\n### 【必须修复】以下变式问题必须改正：")
            for i, item in enumerate(must_fix, 1):
                qid = item.get("question_id", "未知")
                action = item.get("action", "")
                direction = item.get("rewrite_direction", "")
                feedback_parts.append("%d. 变式 %s：" % (i, qid))
                if action:
                    feedback_parts.append("   - 问题：%s" % action)
                if direction:
                    feedback_parts.append("   - 修改方向：%s" % direction)

        should_fix = feedback.get("should_fix", [])
        if should_fix:
            feedback_parts.append("\n### 【建议修复】以下变式问题建议改正：")
            for i, item in enumerate(should_fix, 1):
                qid = item.get("question_id", "未知")
                action = item.get("action", "")
                direction = item.get("rewrite_direction", "")
                feedback_parts.append("%d. 变式 %s：" % (i, qid))
                if action:
                    feedback_parts.append("   - 问题：%s" % action)
                if direction:
                    feedback_parts.append("   - 修改方向：%s" % direction)

        issues = vr.get("issues", [])
        if issues and not must_fix:
            feedback_parts.append("\n### 发现的问题：")
            for issue in issues[:5]:
                qid = issue.get("question_id", "")
                severity = issue.get("severity", "")
                issue_type = issue.get("issue_type", "")
                desc = issue.get("description", "")
                suggestion = issue.get("suggestion", "")
                feedback_parts.append("- [%s] %s (%s): %s" % (severity.upper(), qid, issue_type, desc))
                if suggestion:
                    feedback_parts.append("  建议：%s" % suggestion)

        feedback_parts.append("")

    if feedback_parts:
        feedback_parts.insert(0, "\n" + "=" * 50)
        feedback_parts.insert(1, "# 重要：请根据以下校验反馈修改变式问题")
        feedback_parts.append("请在生成时严格按照上述反馈进行修改，确保所有【必须修复】的问题都得到解决。")
        feedback_parts.append("=" * 50 + "\n")

    return "\n".join(feedback_parts)


def variant_question_node(state: dict) -> dict:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    validation_feedback = _format_validation_feedback(state)
    retry_count = state.get("variant_retry_count", 0)
    previous_variant_questions = state.get("variant_questions", []) if retry_count > 0 else []

    map_logic = state.get("map_construction_logic", {})
    variant_plans = map_logic.get("variant_question_plans", [])

    prompt = prompt_template.replace("{subject}", state.get("subject", ""))
    prompt = prompt.replace("{grade}", state.get("grade", ""))
    prompt = prompt.replace("{language_style}", state.get("language_style", ""))
    prompt = prompt.replace("{main_questions}", json.dumps(state.get("main_questions", []), ensure_ascii=False, indent=2))
    prompt = prompt.replace("{variant_question_plan}", json.dumps(variant_plans, ensure_ascii=False, indent=2))
    prompt = prompt.replace("{previous_questions}", json.dumps(previous_variant_questions, ensure_ascii=False, indent=2))
    prompt = prompt.replace("{validation_feedback}", validation_feedback)

    llm = get_llm(temperature=0.8)
    response = llm.invoke(prompt)
    content = response.content

    variant_questions = _parse_variant_questions(content)

    fallback_used = False
    if not variant_questions and retry_count > 0 and previous_variant_questions:
        # 重试阶段解析失败或输出空数组时，保留上一轮结果避免“清零”连锁反应
        variant_questions = previous_variant_questions
        fallback_used = True

    for q in variant_questions:
        q["question_type"] = "variant"

    msg = "[变式问题生成Agent] 生成了 %d 个变式问题" % len(variant_questions)
    if retry_count > 0:
        msg += "（第 %d 次重试）" % retry_count
    if fallback_used:
        msg += "（本轮输出解析失败，沿用上一轮结果）"

    return {
        "variant_questions": variant_questions,
        "progress_messages": [msg],
    }


def _parse_variant_questions(content: str) -> list:
    text = (content or "").strip()
    if not text:
        return []

    candidates = []

    if "```json" in text:
        try:
            candidates.append(text.split("```json", 1)[1].split("```", 1)[0].strip())
        except IndexError:
            pass
    if "```" in text:
        try:
            candidates.append(text.split("```", 1)[1].split("```", 1)[0].strip())
        except IndexError:
            pass

    candidates.append(text)

    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        candidates.append(match.group(0))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                for key in ("variant_questions", "questions", "data"):
                    value = parsed.get(key)
                    if isinstance(value, list):
                        return value
        except Exception:
            continue

    return []
