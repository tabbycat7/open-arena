"""Agent 2.1.1b — 教学地图逻辑规划Agent"""

import json
import os
from agents.llm import get_generator_llm, get_state_temperature

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
    prompt = prompt.replace("{attachment}", state.get("attachment", ""))

    llm = get_generator_llm(temperature=get_state_temperature(state, default=0.5))
    response = llm.invoke(prompt)
    content = response.content

    try:
        json_str = content
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]
        map_logic = json.loads(json_str.strip())
        map_logic = _normalize_map_logic_ids(map_logic)
    except (json.JSONDecodeError, IndexError):
        map_logic = {"raw_response": content}

    return {
        "map_construction_logic": map_logic,
        "progress_messages": ["[教学地图逻辑规划Agent] 完成教学地图构建蓝图"],
    }


def _normalize_map_logic_ids(map_logic: dict) -> dict:
    if not isinstance(map_logic, dict):
        return map_logic

    main_chain = map_logic.get("main_question_chain")
    if isinstance(main_chain, list):
        for item in main_chain:
            if isinstance(item, dict) and not item.get("id"):
                item["id"] = ""

    variant_plans = map_logic.get("variant_question_plans")
    if isinstance(variant_plans, list):
        for item in variant_plans:
            if not isinstance(item, dict):
                continue
            if not item.get("id"):
                item["id"] = ""
            if not item.get("main_id"):
                item["main_id"] = item.get("for_main_node") or item.get("parent_id") or ""

    scaffold_plans = map_logic.get("scaffold_question_plans")
    if isinstance(scaffold_plans, list):
        for item in scaffold_plans:
            if not isinstance(item, dict):
                continue
            if not item.get("id"):
                item["id"] = ""
            if not item.get("from_id"):
                item["from_id"] = item.get("from_main") or item.get("from_main_id") or ""
            if not item.get("to_id"):
                item["to_id"] = item.get("to_main") or item.get("to_main_id") or ""

    return map_logic
