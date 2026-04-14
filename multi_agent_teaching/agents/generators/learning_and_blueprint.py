"""Agent 2.1.1 — 学情分析与教学蓝图规划Agent（合并）

将原"学情与目标解析Agent"和"教学地图逻辑规划Agent"合并为一个智能体，
一次性完成学情分析和教学蓝图规划。
"""

import json
import os
from agents.llm import get_generator_llm, get_state_temperature

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "learning_and_blueprint.txt")


def learning_and_blueprint_node(state: dict) -> dict:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    prompt = prompt_template.replace("{subject}", state.get("subject", ""))
    prompt = prompt.replace("{grade}", state.get("grade", ""))
    prompt = prompt.replace("{teaching_goals}", state.get("teaching_goals", ""))
    prompt = prompt.replace("{student_profile}", state.get("student_profile", ""))
    prompt = prompt.replace("{difficulty_analysis}", state.get("difficulty_analysis", ""))
    prompt = prompt.replace("{attachment}", state.get("attachment", ""))

    llm = get_generator_llm(temperature=get_state_temperature(state, default=0.4))
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
        result = {"raw_response": content}

    analysis_result = _extract_analysis_result(result)
    map_logic = _extract_map_logic(result)
    map_logic = _normalize_map_logic_ids(map_logic)

    return {
        "analysis_result": analysis_result,
        "map_construction_logic": map_logic,
        "progress_messages": ["[学情分析与教学蓝图规划Agent] 完成学情分析与教学蓝图规划"],
    }


def _extract_analysis_result(result: dict) -> dict:
    """从合并结果中提取学情分析部分"""
    if not isinstance(result, dict):
        return result

    analysis_keys = [
        "subject_grade",
        "material_analysis",
        "teaching_goals_breakdown",
        "knowledge_graph",
        "student_profile_analysis",
        "teaching_focus",
        "goal_situation_alignment",
    ]

    if "analysis_result" in result:
        return result["analysis_result"]

    analysis = {}
    for key in analysis_keys:
        if key in result:
            analysis[key] = result[key]

    if analysis:
        return analysis

    return result


def _extract_map_logic(result: dict) -> dict:
    """从合并结果中提取教学蓝图部分"""
    if not isinstance(result, dict):
        return {}

    blueprint_keys = [
        "teaching_process",
        "main_question_chain",
        "variant_question_plans",
        "scaffold_question_plans",
        "coverage_report",
    ]

    if "map_construction_logic" in result:
        return result["map_construction_logic"]

    if "blueprint" in result:
        return result["blueprint"]

    blueprint = {}
    for key in blueprint_keys:
        if key in result:
            blueprint[key] = result[key]

    if blueprint:
        return blueprint

    return {}


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
