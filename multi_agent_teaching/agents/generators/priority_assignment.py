"""Agent — 调度优先级分配Agent

基于学情分析和教学地图蓝图，为教学地图中的每个问题节点分配调度优先级（priority）。
优先级将替代边权，作为导航算法选择候选节点的依据。
"""

import json
import os
from typing import Dict

from agents.llm import get_generator_llm, get_state_temperature

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "priority_assignment.txt")

_TYPE_DEFAULTS: Dict[str, float] = {"main": 1.0, "variant": 0.8, "scaffold": 0.7}


def priority_assignment_node(state: dict) -> dict:
    teaching_map = state.get("teaching_map", {})
    nodes = teaching_map.get("nodes", [])

    if not nodes:
        return {
            "teaching_map": teaching_map,
            "progress_messages": ["[调度优先级分配Agent] 教学地图为空，跳过优先级分配"],
        }

    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    prompt = prompt_template.replace(
        "{teaching_map}",
        json.dumps(teaching_map, ensure_ascii=False, indent=2),
    )
    prompt = prompt.replace(
        "{analysis_result}",
        json.dumps(state.get("analysis_result", {}), ensure_ascii=False, indent=2),
    )
    prompt = prompt.replace(
        "{map_construction_logic}",
        json.dumps(state.get("map_construction_logic", {}), ensure_ascii=False, indent=2),
    )

    llm = get_generator_llm(temperature=get_state_temperature(state, default=0.3))
    response = llm.invoke(prompt)
    content = response.content

    priority_map = _parse_priority_response(content)

    updated_nodes = []
    assigned_count = 0
    for node in nodes:
        node_copy = dict(node)
        node_id = node_copy.get("id", "")
        if node_id in priority_map:
            node_copy["priority"] = priority_map[node_id]
            assigned_count += 1
        else:
            node_copy["priority"] = _TYPE_DEFAULTS.get(
                node_copy.get("question_type", "main"), 0.5
            )
        updated_nodes.append(node_copy)

    updated_map = dict(teaching_map)
    updated_map["nodes"] = updated_nodes

    return {
        "teaching_map": updated_map,
        "progress_messages": [
            "[调度优先级分配Agent] 完成优先级分配：%d/%d 个节点由 LLM 赋值，其余使用默认值"
            % (assigned_count, len(nodes))
        ],
    }


def _parse_priority_response(content: str) -> Dict[str, float]:
    """Parse LLM response into {node_id: priority} mapping."""
    try:
        json_str = content
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]
        data = json.loads(json_str.strip())
    except (json.JSONDecodeError, IndexError):
        return {}

    assignments = data.get("priority_assignments", [])
    if not isinstance(assignments, list):
        return {}

    result: Dict[str, float] = {}
    for item in assignments:
        if not isinstance(item, dict):
            continue
        node_id = item.get("node_id", "")
        priority = item.get("priority")
        if not node_id or priority is None:
            continue
        try:
            pri_val = float(priority)
            pri_val = max(0.0, min(1.0, pri_val))
            result[node_id] = pri_val
        except (TypeError, ValueError):
            continue

    return result
