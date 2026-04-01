"""Agent 2.1.1 — 学情与目标解析Agent"""

import json
import os
from agents.llm import get_llm

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "learning_analysis.txt")


def learning_analysis_node(state: dict) -> dict:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    prompt = prompt_template.replace("{subject}", state.get("subject", ""))
    prompt = prompt.replace("{grade}", state.get("grade", ""))
    prompt = prompt.replace("{teaching_goals}", state.get("teaching_goals", ""))
    prompt = prompt.replace("{student_profile}", state.get("student_profile", ""))
    prompt = prompt.replace("{attachment}", state.get("attachment", ""))

    llm = get_llm(temperature=0.3)
    response = llm.invoke(prompt)
    content = response.content

    try:
        json_str = content
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]
        analysis_result = json.loads(json_str.strip())
    except (json.JSONDecodeError, IndexError):
        analysis_result = {"raw_response": content}

    return {
        "analysis_result": analysis_result,
        "progress_messages": ["[学情与目标解析Agent] 完成学情分析与教学目标解析"],
    }
