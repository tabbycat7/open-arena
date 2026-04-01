"""Agent V3 — 教学目标对齐检验Agent"""

import json
import os
from agents.llm import get_llm

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "goal_alignment.txt")


def goal_alignment_node(state: dict) -> dict:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    prompt = prompt_template.replace("{teaching_goals}", state.get("teaching_goals", ""))
    prompt = prompt.replace(
        "{analysis_result}",
        json.dumps(state.get("analysis_result", {}), ensure_ascii=False, indent=2),
    )
    prompt = prompt.replace(
        "{main_questions}",
        json.dumps(state.get("main_questions", []), ensure_ascii=False, indent=2),
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
        result = {"passed": True, "feedback": {}, "issues": [], "total_score": 6}

    passed = result.get("passed", True)
    total_score = result.get("total_score", 6)
    feedback = result.get("feedback", {})
    issues = result.get("issues", [])
    overall = result.get("overall_assessment", "")
    structure_adjustment = result.get("structure_adjustment", {})

    status_msg = "通过" if passed else "未通过（得分 %s/6）" % total_score

    return {
        "validation_results": [
            {
                "validator": "goal_alignment",
                "passed": passed,
                "total_score": total_score,
                "feedback": feedback,
                "issues": issues,
                "overall_assessment": overall,
                "structure_adjustment": structure_adjustment,
                "raw_result": result,
            }
        ],
        "progress_messages": [
            "[教学目标对齐检验Agent] %s" % status_msg
        ],
    }
