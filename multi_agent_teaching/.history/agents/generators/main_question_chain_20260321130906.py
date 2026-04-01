"""Agent 2.1.2 — 主干问题链构建Agent"""

import json
import os
from agents.llm import get_llm

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "main_question_chain.txt")


def _format_validation_feedback(state: dict) -> str:
    """从验证结果中提取结构化反馈，格式化为LLM可理解的修改指令"""
    feedback_parts = []

    for vr in state.get("validation_results", []):
        validator = vr.get("validator", "")
        if validator not in ("cognitive_alignment", "goal_alignment"):
            continue
        if vr.get("passed", True):
            continue

        validator_name = "认知对齐检验" if validator == "cognitive_alignment" else "教学目标对齐检验"
        total_score = vr.get("total_score", "?")
        overall = vr.get("overall_assessment", "")

        feedback_parts.append("=" * 50)
        feedback_parts.append("## 上一轮【%s】反馈（得分：%s/8）" % (validator_name, total_score))
        if overall:
            feedback_parts.append("总体评价：%s" % overall)

        feedback = vr.get("feedback", {})

        must_fix = feedback.get("must_fix", [])
        if must_fix:
            feedback_parts.append("\n### 【必须修复】以下问题必须改正：")
            for i, item in enumerate(must_fix, 1):
                node_id = item.get("node_id", "未知")
                action = item.get("action", "")
                direction = item.get("rewrite_direction", "")
                feedback_parts.append("%d. 节点 %s：" % (i, node_id))
                if action:
                    feedback_parts.append("   - 问题：%s" % action)
                if direction:
                    feedback_parts.append("   - 修改方向：%s" % direction)

        should_fix = feedback.get("should_fix", [])
        if should_fix:
            feedback_parts.append("\n### 【建议修复】以下问题建议改正：")
            for i, item in enumerate(should_fix, 1):
                node_id = item.get("node_id", item.get("target_node", "未知"))
                action = item.get("action", "")
                direction = item.get("direction", item.get("rewrite_direction", ""))
                feedback_parts.append("%d. 节点 %s：" % (i, node_id))
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
                desc = issue.get("description", "")
                suggestion = issue.get("suggestion", "")
                feedback_parts.append("- [%s] %s: %s" % (severity.upper(), qid, desc))
                if suggestion:
                    feedback_parts.append("  建议：%s" % suggestion)

        feedback_parts.append("")

    if feedback_parts:
        feedback_parts.insert(0, "\n" + "=" * 50)
        feedback_parts.insert(1, "# 重要：请根据以下校验反馈修改主干问题")
        feedback_parts.append("请在生成时严格按照上述反馈进行修改，确保所有【必须修复】的问题都得到解决。")
        feedback_parts.append("=" * 50 + "\n")

    return "\n".join(feedback_parts)


def main_question_chain_node(state: dict) -> dict:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    validation_feedback = _format_validation_feedback(state)
    retry_count = state.get("main_retry_count", 0)
    previous_main_questions = state.get("main_questions", []) if retry_count > 0 else []

    map_logic = state.get("map_construction_logic", {})
    main_chain_plan = map_logic.get("main_question_chain", [])

    prompt = prompt_template.replace("{subject}", state.get("subject", ""))
    prompt = prompt.replace("{grade}", state.get("grade", ""))
    prompt = prompt.replace("{teaching_goals}", state.get("teaching_goals", ""))
    prompt = prompt.replace("{student_profile}", state.get("student_profile", ""))
    prompt = prompt.replace("{language_style}", state.get("language_style", ""))
    prompt = prompt.replace("{analysis_result}", json.dumps(state.get("analysis_result", {}), ensure_ascii=False, indent=2))
    prompt = prompt.replace("{main_question_plan}", json.dumps(main_chain_plan, ensure_ascii=False, indent=2))
    prompt = prompt.replace("{previous_questions}", json.dumps(previous_main_questions, ensure_ascii=False, indent=2))
    prompt = prompt.replace("{validation_feedback}", validation_feedback)

    llm = get_llm(temperature=0.7)
    response = llm.invoke(prompt)
    content = response.content

    try:
        json_str = content
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]
        main_questions = json.loads(json_str.strip())
    except (json.JSONDecodeError, IndexError):
        main_questions = []

    for q in main_questions:
        q["question_type"] = "main"
        q.setdefault("parent_id", None)

    msg = "[主干问题链构建Agent] 生成了 %d 个主干问题" % len(main_questions)
    if retry_count > 0:
        msg += "（第 %d 次重试）" % retry_count

    return {
        "main_questions": main_questions,
        "validation_results": [],
        "progress_messages": [msg],
    }
