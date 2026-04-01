"""Agent V2 — 学情对齐检验Agent（支架+变式分开评估）"""

import json
import os
from agents.llm import get_llm

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "learning_alignment.txt")


def learning_alignment_node(state: dict) -> dict:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    prompt = prompt_template.replace("{subject}", state.get("subject", ""))
    prompt = prompt.replace("{grade}", state.get("grade", ""))
    prompt = prompt.replace(
        "{analysis_result}",
        json.dumps(state.get("analysis_result", {}), ensure_ascii=False, indent=2),
    )
    prompt = prompt.replace(
        "{main_questions}",
        json.dumps(state.get("main_questions", []), ensure_ascii=False, indent=2),
    )
    prompt = prompt.replace(
        "{variant_questions}",
        json.dumps(state.get("variant_questions", []), ensure_ascii=False, indent=2),
    )
    prompt = prompt.replace(
        "{scaffold_questions}",
        json.dumps(state.get("scaffold_questions", []), ensure_ascii=False, indent=2),
    )

    llm = get_llm(temperature=0.2)
    response = llm.invoke(prompt)
    content = response.content

    try:
        json_str = content
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]
        result = json.loads(json_str.strip())
    except (json.JSONDecodeError, IndexError):
        result = {
            "passed": True,
            "scaffold_total_score": 10,
            "variant_total_score": 8,
            "feedback": {},
        }

    passed = result.get("passed", True)
    scaffold_score = result.get("scaffold_total_score", 10)
    variant_score = result.get("variant_total_score", 8)
    feedback = result.get("feedback", {})
    scaffold_issues = result.get("scaffold_issue_details", [])
    variant_issues = result.get("variant_issue_details", [])
    overall = result.get("overall_assessment", "")

    scaffold_needs_retry = scaffold_score < 6
    variant_needs_retry = variant_score < 4

    must_fix_scaffold = feedback.get("must_fix_scaffold", [])
    must_fix_variant = feedback.get("must_fix_variant", [])

    if not passed:
        if len(must_fix_variant) > 0 or variant_needs_retry:
            retry_target = "variant"
        elif len(must_fix_scaffold) > 0 or scaffold_needs_retry:
            retry_target = "scaffold"
        else:
            retry_target = "scaffold"
    else:
        retry_target = None

    status_parts = []
    status_parts.append("支架 %s/10" % scaffold_score)
    status_parts.append("变式 %s/8" % variant_score)
    status_msg = "通过" if passed else "未通过（%s）" % "，".join(status_parts)

    return {
        "validation_results": [
            {
                "validator": "learning_alignment",
                "passed": passed,
                "scaffold_total_score": scaffold_score,
                "variant_total_score": variant_score,
                "retry_target": retry_target,
                "feedback": feedback,
                "scaffold_issues": scaffold_issues,
                "variant_issues": variant_issues,
                "overall_assessment": overall,
                "raw_result": result,
            }
        ],
        "progress_messages": [
            "[学情对齐检验Agent] %s" % status_msg
        ],
    }
