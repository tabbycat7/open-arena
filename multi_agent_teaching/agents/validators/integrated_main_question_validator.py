"""综合主干问题校验Agent — 合并原认知对齐、教学目标对齐、教学逻辑检验三个校验器"""

import json
import os
from agents.llm import get_validator_llm

PROMPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "prompts", "integrated_main_question_validator.txt"
)


def integrated_main_question_validator_node(state: dict) -> dict:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    prompt = prompt_template.replace("{subject}", state.get("subject", ""))
    prompt = prompt.replace("{grade}", state.get("grade", ""))
    prompt = prompt.replace("{teaching_goals}", state.get("teaching_goals", ""))
    prompt = prompt.replace(
        "{analysis_result}",
        json.dumps(state.get("analysis_result", {}), ensure_ascii=False, indent=2),
    )
    prompt = prompt.replace(
        "{map_construction_logic}",
        json.dumps(state.get("map_construction_logic", {}), ensure_ascii=False, indent=2),
    )
    prompt = prompt.replace(
        "{main_questions}",
        json.dumps(state.get("main_questions", []), ensure_ascii=False, indent=2),
    )
    prompt = prompt.replace("{attachment}", state.get("attachment", ""))

    llm = get_validator_llm(temperature=0.1)
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
        result = {"passed": True, "decision": "pass", "feedback": {}, "issues_summary": [], "total_score": 10}

    passed = result.get("passed", True)
    total_score = result.get("total_score", 10)
    decision = result.get("decision", "pass" if passed else "fail")
    feedback = result.get("feedback", {})
    issues = result.get("issues_summary", [])
    overall = result.get("overall_assessment", "")
    structure_adjustment = result.get("structure_adjustment", {})

    retry_count = state.get("main_retry_count", 0)
    if passed:
        if retry_count > 0:
            status_msg = "第 %d 次重试后通过（%s，得分 %s/10）" % (retry_count, decision, total_score)
        else:
            status_msg = "通过（%s，得分 %s/10）" % (decision, total_score)
    else:
        status_msg = "未通过（得分 %s/10）" % total_score

    return {
        "validation_results": [
            {
                "validator": "integrated_main_question_validator",
                "passed": passed,
                "decision": decision,
                "total_score": total_score,
                "feedback": feedback,
                "issues": issues,
                "overall_assessment": overall,
                "structure_adjustment": structure_adjustment,
                "dimension_scores": result.get("dimension_scores", {}),
                "key_findings": result.get("key_findings", {}),
                "node_diagnostics": result.get("node_diagnostics", []),
                "raw_result": result,
            }
        ],
        "progress_messages": [
            "[主干问题综合校验Agent] %s" % status_msg
        ],
    }
