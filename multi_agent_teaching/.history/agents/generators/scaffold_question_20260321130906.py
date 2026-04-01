"""Agent 2.1.4 — 支架问题生成Agent"""

import json
import os
import re
from agents.llm import get_llm


def _infer_bridge_from_id(scaffold_id, main_ids):
    """
    根据支架问题 ID 推断其桥接的主干节点。
    例如：S1-1 → from M1 to M2
          S2-1 → from M2 to M3
    """
    match = re.match(r'S(\d+)', scaffold_id)
    if not match:
        return "", ""

    bridge_num = int(match.group(1))
    from_main = "M%d" % bridge_num
    to_main = "M%d" % (bridge_num + 1)

    if from_main not in main_ids:
        sorted_main = sorted([m for m in main_ids if m.startswith("M")],
                             key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0)
        if bridge_num - 1 < len(sorted_main):
            from_main = sorted_main[bridge_num - 1]
        if bridge_num < len(sorted_main):
            to_main = sorted_main[bridge_num]

    return from_main, to_main

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "scaffold_question.txt")


def _format_validation_feedback(state: dict) -> str:
    """从验证结果中提取支架问题相关的反馈"""
    feedback_parts = []

    for vr in state.get("validation_results", []):
        validator = vr.get("validator", "")
        if validator == "learning_alignment":
            if vr.get("passed", True):
                continue

            scaffold_score = vr.get("scaffold_total_score", "?")
            overall = vr.get("overall_assessment", "")

            feedback_parts.append("=" * 50)
            feedback_parts.append("## 上一轮【学情对齐检验-支架部分】反馈（得分：%s/10）" % scaffold_score)
            if overall:
                feedback_parts.append("总体评价：%s" % overall)

            feedback = vr.get("feedback", {})

            must_fix = feedback.get("must_fix_scaffold", [])
            if must_fix:
                feedback_parts.append("\n### 【必须修复】以下支架问题必须改正：")
                for i, item in enumerate(must_fix, 1):
                    qid = item.get("question_id", "未知")
                    action = item.get("action", "")
                    direction = item.get("rewrite_direction", "")
                    feedback_parts.append("%d. 支架 %s：" % (i, qid))
                    if action:
                        feedback_parts.append("   - 问题：%s" % action)
                    if direction:
                        feedback_parts.append("   - 修改方向：%s" % direction)

            should_fix = feedback.get("should_fix_scaffold", [])
            if should_fix:
                feedback_parts.append("\n### 【建议修复】以下支架问题建议改正：")
                for i, item in enumerate(should_fix, 1):
                    qid = item.get("question_id", "未知")
                    action = item.get("action", "")
                    direction = item.get("rewrite_direction", "")
                    feedback_parts.append("%d. 支架 %s：" % (i, qid))
                    if action:
                        feedback_parts.append("   - 问题：%s" % action)
                    if direction:
                        feedback_parts.append("   - 修改方向：%s" % direction)

            scaffold_issues = vr.get("scaffold_issues", [])
            if scaffold_issues and not must_fix:
                feedback_parts.append("\n### 发现的支架问题：")
                for issue in scaffold_issues[:5]:
                    qid = issue.get("question_id", "")
                    severity = issue.get("severity", "")
                    issue_type = issue.get("issue_type", "")
                    desc = issue.get("description", "")
                    suggestion = issue.get("suggestion", "")
                    feedback_parts.append("- [%s] %s (%s): %s" % (severity.upper(), qid, issue_type, desc))
                    if suggestion:
                        feedback_parts.append("  建议：%s" % suggestion)

            feedback_parts.append("")

        elif validator == "logic_alignment":
            if vr.get("passed", True):
                continue

            total_score = vr.get("total_score", "?")
            overall = vr.get("overall_assessment", "")

            feedback_parts.append("=" * 50)
            feedback_parts.append("## 上一轮【支架逻辑检验】反馈（得分：%s/8）" % total_score)
            if overall:
                feedback_parts.append("总体评价：%s" % overall)

            feedback = vr.get("feedback", {})

            must_fix = feedback.get("must_fix", [])
            if must_fix:
                feedback_parts.append("\n### 【必须修复】：")
                for i, item in enumerate(must_fix, 1):
                    bridge = item.get("bridge", "")
                    action = item.get("action", "")
                    direction = item.get("rewrite_direction", "")
                    feedback_parts.append("%d. 桥接 %s：" % (i, bridge))
                    if action:
                        feedback_parts.append("   - 问题：%s" % action)
                    if direction:
                        feedback_parts.append("   - 修改方向：%s" % direction)

            should_fix = feedback.get("should_fix", [])
            if should_fix:
                feedback_parts.append("\n### 【建议修复】：")
                for i, item in enumerate(should_fix, 1):
                    bridge = item.get("bridge", "")
                    action = item.get("action", "")
                    direction = item.get("rewrite_direction", "")
                    feedback_parts.append("%d. 桥接 %s：" % (i, bridge))
                    if action:
                        feedback_parts.append("   - 问题：%s" % action)
                    if direction:
                        feedback_parts.append("   - 修改方向：%s" % direction)

            issues = vr.get("issues", [])
            if issues and not must_fix:
                feedback_parts.append("\n### 发现的支架逻辑问题：")
                for issue in issues[:5]:
                    bridge = issue.get("bridge", "")
                    related = issue.get("related_questions", [])
                    severity = issue.get("severity", "")
                    issue_type = issue.get("issue_type", "")
                    desc = issue.get("description", "")
                    suggestion = issue.get("suggestion", "")
                    loc = bridge if bridge else ", ".join(related) if related else ""
                    feedback_parts.append("- [%s] %s (%s): %s" % (severity.upper(), loc, issue_type, desc))
                    if suggestion:
                        feedback_parts.append("  建议：%s" % suggestion)

            feedback_parts.append("")

    if feedback_parts:
        feedback_parts.insert(0, "\n" + "=" * 50)
        feedback_parts.insert(1, "# 重要：请根据以下校验反馈修改支架问题")
        feedback_parts.append("请在生成时严格按照上述反馈进行修改，确保所有【必须修复】的问题都得到解决。")
        feedback_parts.append("=" * 50 + "\n")

    return "\n".join(feedback_parts)


def scaffold_question_node(state: dict) -> dict:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    validation_feedback = _format_validation_feedback(state)
    retry_count = state.get("scaffold_retry_count", 0)
    previous_scaffold_questions = state.get("scaffold_questions", []) if retry_count > 0 else []

    map_logic = state.get("map_construction_logic", {})
    scaffold_plans = map_logic.get("scaffold_question_plans", [])

    prompt = prompt_template.replace("{subject}", state.get("subject", ""))
    prompt = prompt.replace("{grade}", state.get("grade", ""))
    prompt = prompt.replace("{language_style}", state.get("language_style", ""))
    prompt = prompt.replace("{main_questions}", json.dumps(state.get("main_questions", []), ensure_ascii=False, indent=2))
    prompt = prompt.replace("{scaffold_question_plan}", json.dumps(scaffold_plans, ensure_ascii=False, indent=2))
    prompt = prompt.replace("{previous_questions}", json.dumps(previous_scaffold_questions, ensure_ascii=False, indent=2))
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
        scaffold_questions = json.loads(json_str.strip())
    except (json.JSONDecodeError, IndexError):
        scaffold_questions = []

    main_ids = [m.get("id", "") for m in state.get("main_questions", [])]

    for q in scaffold_questions:
        q["question_type"] = "scaffold"

        if not q.get("from_main_id") or not q.get("to_main_id"):
            inferred_from, inferred_to = _infer_bridge_from_id(q.get("id", ""), main_ids)
            if not q.get("from_main_id"):
                q["from_main_id"] = inferred_from
            if not q.get("to_main_id"):
                q["to_main_id"] = inferred_to

        q.setdefault("parent_id", q.get("from_main_id"))

    msg = "[支架问题生成Agent] 生成了 %d 个支架问题" % len(scaffold_questions)
    if retry_count > 0:
        msg += "（第 %d 次重试）" % retry_count

    return {
        "scaffold_questions": scaffold_questions,
        "progress_messages": [msg],
    }
