"""Agent 2.1.4 — 支架问题生成Agent"""

import json
import os
import re
from agents.llm import get_generator_llm


def _infer_bridge_from_id(item_id, main_ids):
    """
    根据支架问题 ID 推断其桥接的主干节点。
    例如：S1-1 → from M1 to M2
          S2-1 → from M2 to M3
    """
    match = re.match(r'S(\d+)', item_id)
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


def _pick_item_id(item: dict, default: str = "未知") -> str:
    return (
        item.get("id")
        or item.get("question_id")
        or item.get("target")
        or default
    )


def _extract_bridge_ids(q: dict) -> tuple[str, str]:
    from_id = (
        q.get("from_id")
        or q.get("source_main_question")
        or q.get("from_main_question")
        or q.get("from_main_id")
    )
    to_id = (
        q.get("to_id")
        or q.get("target_main_question")
        or q.get("to_main_question")
        or q.get("to_main_id")
    )
    return from_id or "", to_id or ""


def _format_validation_feedback(state: dict) -> str:
    """从验证结果中提取支架问题相关的反馈（来自 scaffold_alignment）"""
    feedback_parts = []

    for vr in state.get("validation_results", []):
        if vr.get("validator") != "scaffold_alignment":
            continue
        if vr.get("passed", True):
            continue

        total_score = vr.get("total_score", "?")
        overall = vr.get("overall_assessment", "")

        feedback_parts.append("=" * 50)
        feedback_parts.append("## 上一轮【支架问题检验】反馈（得分：%s/10）" % total_score)
        if overall:
            feedback_parts.append("总体评价：%s" % overall)

        feedback = vr.get("feedback", {})

        must_fix = feedback.get("must_fix", [])
        if must_fix:
            feedback_parts.append("\n### 【必须修复】以下支架问题必须改正：")
            for i, item in enumerate(must_fix, 1):
                qid = _pick_item_id(item)
                action = item.get("action", "")
                direction = item.get("rewrite_direction", "")
                feedback_parts.append("%d. 支架 %s：" % (i, qid))
                if action:
                    feedback_parts.append("   - 问题：%s" % action)
                if direction:
                    feedback_parts.append("   - 修改方向：%s" % direction)

        should_fix = feedback.get("should_fix", [])
        if should_fix:
            feedback_parts.append("\n### 【建议修复】以下支架问题建议改正：")
            for i, item in enumerate(should_fix, 1):
                qid = _pick_item_id(item)
                action = item.get("action", "")
                direction = item.get("rewrite_direction", "")
                feedback_parts.append("%d. 支架 %s：" % (i, qid))
                if action:
                    feedback_parts.append("   - 问题：%s" % action)
                if direction:
                    feedback_parts.append("   - 修改方向：%s" % direction)

        issues = vr.get("issues", [])
        if issues and not must_fix:
            feedback_parts.append("\n### 发现的问题：")
            for issue in issues[:5]:
                qid = _pick_item_id(issue, "")
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
        feedback_parts.insert(1, "# 重要：请根据以下校验反馈修改支架问题")
        feedback_parts.append("请在生成时严格按照上述反馈进行修改，确保所有【必须修复】的问题都得到解决。")
        feedback_parts.append("=" * 50 + "\n")

    return "\n".join(feedback_parts)


def scaffold_question_node(state: dict) -> dict:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    # 优先从专用暂存字段读取（bump_scaffold_retry 在清空前保存到此）
    feedback_source = {"validation_results": state.get("scaffold_validation_feedback") or state.get("validation_results", [])}
    validation_feedback = _format_validation_feedback(feedback_source)
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

    llm = get_generator_llm(temperature=0.7)
    response = llm.invoke(prompt)
    content = response.content

    scaffold_questions = _parse_scaffold_questions(content)

    main_ids = [m.get("id", "") for m in state.get("main_questions", [])]

    for q in scaffold_questions:
        if not q.get("id"):
            q["id"] = ""
        q["question_type"] = "scaffold"

        from_id, to_id = _extract_bridge_ids(q)
        if not from_id or not to_id:
            inferred_from, inferred_to = _infer_bridge_from_id(q.get("id", ""), main_ids)
            from_id = from_id or inferred_from
            to_id = to_id or inferred_to

        if from_id:
            q["from_id"] = from_id
            q.setdefault("from_main_id", from_id)
            q.setdefault("main_id", from_id)
            q.setdefault("parent_id", from_id)
        if to_id:
            q["to_id"] = to_id
            q.setdefault("to_main_id", to_id)

    msg = "[支架问题生成Agent] 生成了 %d 个支架问题" % len(scaffold_questions)
    if retry_count > 0:
        msg += "（第 %d 次重试）" % retry_count

    return {
        "scaffold_questions": scaffold_questions,
        "progress_messages": [msg],
    }


def _parse_scaffold_questions(content: str) -> list:
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
                for key in ("scaffold_questions", "questions", "data"):
                    value = parsed.get(key)
                    if isinstance(value, list):
                        return value
        except Exception:
            continue

    return []
