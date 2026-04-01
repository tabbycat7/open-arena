"""Agent 2.1.1b — 教学地图逻辑规划Agent"""

import json
import os
from agents.llm import get_llm

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "teaching_logic_design.txt")


def teaching_logic_design_node(state: dict) -> dict:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    prompt = prompt_template.replace("{subject}", state.get("subject", ""))
    prompt = prompt.replace("{grade}", state.get("grade", ""))
    prompt = prompt.replace("{teaching_goals}", state.get("teaching_goals", ""))
    prompt = prompt.replace(
        "{analysis_result}",
        json.dumps(state.get("analysis_result", {}), ensure_ascii=False, indent=2),
    )

    llm = get_llm(temperature=0.5)
    response = llm.invoke(prompt)
    content = response.content

    try:
        json_str = content
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]
        map_logic = json.loads(json_str.strip())
    except (json.JSONDecodeError, IndexError):
        map_logic = {"raw_response": content}

    return {
        "map_construction_logic": map_logic,
        "progress_messages": ["[教学地图逻辑规划Agent] 完成教学地图构建蓝图"],
    }
