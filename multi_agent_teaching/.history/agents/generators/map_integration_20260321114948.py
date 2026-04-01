"""Agent 2.1.5 — 教学地图整合Agent

这个 Agent 不使用 LLM，而是用确定性代码将所有问题整合为教学地图。
这样可以确保问题内容不被修改或丢失。
"""

import re
from collections import defaultdict


def map_integration_node(state: dict) -> dict:
    main_qs = state.get("main_questions", [])
    variant_qs = state.get("variant_questions", [])
    scaffold_qs = state.get("scaffold_questions", [])

    nodes = []
    edges = []

    for q in main_qs:
        cognitive_level = q.get("cognitive_level") or q.get("bloom_level", "")
        nodes.append({
            "id": q.get("id", ""),
            "content": q.get("content", ""),
            "question_type": "main",
            "knowledge_points": q.get("knowledge_points", []),
            "cognitive_level": cognitive_level,
            "difficulty": q.get("difficulty", 0.5),
            "design_rationale": q.get("design_rationale", ""),
        })

    for q in variant_qs:
        cognitive_level = q.get("cognitive_level") or q.get("bloom_level", "")
        nodes.append({
            "id": q.get("id", ""),
            "content": q.get("content", ""),
            "question_type": "variant",
            "knowledge_points": q.get("knowledge_points", []),
            "cognitive_level": cognitive_level,
            "difficulty": q.get("difficulty", 0.5),
            "parent_id": q.get("parent_id", ""),
            "variation_type": q.get("variation_type", ""),
            "design_rationale": q.get("design_rationale", ""),
        })

    for q in scaffold_qs:
        cognitive_level = q.get("cognitive_level") or q.get("bloom_level", "")
        nodes.append({
            "id": q.get("id", ""),
            "content": q.get("content", ""),
            "question_type": "scaffold",
            "knowledge_points": q.get("knowledge_points", []),
            "cognitive_level": cognitive_level,
            "difficulty": q.get("difficulty", 0.3),
            "from_main_id": q.get("from_main_id", ""),
            "to_main_id": q.get("to_main_id", ""),
            "bridge_function": q.get("bridge_function", ""),
            "design_rationale": q.get("design_rationale", ""),
        })

    sorted_main = sorted(main_qs, key=lambda x: _extract_number(x.get("id", "M0")))
    for i in range(len(sorted_main) - 1):
        edges.append({
            "source": sorted_main[i].get("id", ""),
            "target": sorted_main[i + 1].get("id", ""),
            "relation": "sequence",
            "weight": 1.0,
        })

    for vq in variant_qs:
        parent_id = vq.get("parent_id", "")
        if parent_id:
            edges.append({
                "source": parent_id,
                "target": vq.get("id", ""),
                "relation": "variant_of",
                "weight": 0.8,
            })

    bridge_groups = defaultdict(list)
    for sq in scaffold_qs:
        from_id = sq.get("from_main_id", "")
        to_id = sq.get("to_main_id", "")
        if from_id and to_id:
            bridge_key = (from_id, to_id)
            bridge_groups[bridge_key].append(sq)

    for (from_main, to_main), scaffolds in bridge_groups.items():
        sorted_scaffolds = sorted(scaffolds, key=lambda x: _extract_scaffold_seq(x.get("id", "")))

        if len(sorted_scaffolds) == 0:
            continue

        first_scaffold = sorted_scaffolds[0]
        edges.append({
            "source": from_main,
            "target": first_scaffold.get("id", ""),
            "relation": "scaffold_from",
            "weight": 0.7,
        })

        for i in range(len(sorted_scaffolds) - 1):
            edges.append({
                "source": sorted_scaffolds[i].get("id", ""),
                "target": sorted_scaffolds[i + 1].get("id", ""),
                "relation": "scaffold_sequence",
                "weight": 0.7,
            })

        last_scaffold = sorted_scaffolds[-1]
        edges.append({
            "source": last_scaffold.get("id", ""),
            "target": to_main,
            "relation": "scaffold_to",
            "weight": 0.7,
        })

    teaching_map = {"nodes": nodes, "edges": edges}

    node_count = len(nodes)
    edge_count = len(edges)
    main_count = len(main_qs)
    variant_count = len(variant_qs)
    scaffold_count = len(scaffold_qs)

    return {
        "teaching_map": teaching_map,
        "progress_messages": [
            "[教学地图整合Agent] 整合完成：%d 个节点（主干 %d、变式 %d、支架 %d），%d 条边" % (
                node_count, main_count, variant_count, scaffold_count, edge_count
            )
        ],
    }


def _extract_number(node_id: str) -> int:
    """从节点 ID 中提取第一个数字用于排序，如 M1 -> 1, M10 -> 10"""
    match = re.search(r'\d+', node_id)
    if match:
        return int(match.group())
    return 0


def _extract_scaffold_seq(scaffold_id: str) -> tuple:
    """
    从支架问题 ID 中提取排序元组。
    例如：S1-1 -> (1, 1), S1-2 -> (1, 2), S2-1 -> (2, 1)
    """
    match = re.match(r'S(\d+)-(\d+)', scaffold_id)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    match2 = re.search(r'(\d+)', scaffold_id)
    if match2:
        return (int(match2.group(1)), 0)
    return (999, 999)
