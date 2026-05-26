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
        design_intent = q.get("design_intent") or q.get("design_rationale", "")
        lesson_presentation_script = q.get("lesson_presentation_script") or q.get("commentary") or q.get("Commentary", "")
        nodes.append({
            "id": q.get("id", ""),
            "content": q.get("content", ""),
            "question_type": "main",
            "lesson_presentation_script": lesson_presentation_script,
            "explanation": q.get("explanation", ""),
            "knowledge_points": q.get("knowledge_points", []),
            "cognitive_level": cognitive_level,
            "difficulty": q.get("difficulty", 0.5),
            "design_intent": design_intent,
            "design_rationale": q.get("design_rationale", ""),
        })

    for q in variant_qs:
        cognitive_level = q.get("cognitive_level") or q.get("bloom_level", "")
        design_intent = q.get("design_intent") or q.get("design_rationale", "")
        lesson_presentation_script = q.get("lesson_presentation_script") or q.get("commentary") or q.get("Commentary", "")
        main_id = q.get("main_id") or q.get("parent_id") or q.get("linked_main_question", "")
        nodes.append({
            "id": q.get("id", ""),
            "content": q.get("content", ""),
            "question_type": "variant",
            "lesson_presentation_script": lesson_presentation_script,
            "explanation": q.get("explanation", ""),
            "knowledge_points": q.get("knowledge_points", []),
            "cognitive_level": cognitive_level,
            "difficulty": q.get("difficulty", 0.5),
            "main_id": main_id,
            "parent_id": main_id,
            "variation_type": q.get("variation_type", ""),
            "design_intent": design_intent,
            "design_rationale": q.get("design_rationale", ""),
        })

    for q in scaffold_qs:
        cognitive_level = q.get("cognitive_level") or q.get("bloom_level", "")
        design_intent = q.get("design_intent") or q.get("design_rationale", "")
        lesson_presentation_script = q.get("lesson_presentation_script") or q.get("commentary") or q.get("Commentary", "")
        from_id = q.get("from_id") or q.get("from_main_id") or q.get("source_main_question", "")
        to_id = q.get("to_id") or q.get("to_main_id") or q.get("target_main_question", "")
        bridge_group_id = q.get("bridge_group_id", "")
        nodes.append({
            "id": q.get("id", ""),
            "content": q.get("content", ""),
            "question_type": "scaffold",
            "lesson_presentation_script": lesson_presentation_script,
            "explanation": q.get("explanation", ""),
            "knowledge_points": q.get("knowledge_points", []),
            "cognitive_level": cognitive_level,
            "difficulty": q.get("difficulty", 0.3),
            "from_id": from_id,
            "to_id": to_id,
            "from_main_id": from_id,
            "to_main_id": to_id,
            "bridge_group_id": bridge_group_id,
            "bridge_function": q.get("bridge_function", ""),
            "design_intent": design_intent,
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
        main_id = vq.get("main_id") or vq.get("parent_id") or vq.get("linked_main_question", "")
        if main_id:
            edges.append({
                "source": main_id,
                "target": vq.get("id", ""),
                "relation": "variant_of",
                "weight": 0.8,
            })

    bridge_groups = defaultdict(list)
    for sq in scaffold_qs:
        from_id = sq.get("from_id") or sq.get("from_main_id") or sq.get("source_main_question", "")
        to_id = sq.get("to_id") or sq.get("to_main_id") or sq.get("target_main_question", "")
        bg_id = sq.get("bridge_group_id", "")
        if from_id and to_id:
            # Use bridge_group_id as primary key; fall back to (from_id, to_id) for legacy data
            bridge_key = bg_id if bg_id else (from_id, to_id)
            bridge_groups[bridge_key].append(sq)

    for bridge_key, scaffolds in bridge_groups.items():
        sorted_scaffolds = sorted(scaffolds, key=lambda x: _extract_scaffold_seq(x.get("id", "")))

        if len(sorted_scaffolds) == 0:
            continue

        # Derive from_main and to_main from the scaffolds themselves
        first_scaffold = sorted_scaffolds[0]
        from_main = first_scaffold.get("from_id") or first_scaffold.get("from_main_id") or first_scaffold.get("source_main_question", "")
        to_main = first_scaffold.get("to_id") or first_scaffold.get("to_main_id") or first_scaffold.get("target_main_question", "")

        if from_main:
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
        if to_main:
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


def _extract_number(item_id: str) -> int:
    """从节点 ID 中提取第一个数字用于排序，如 M1 -> 1, M10 -> 10"""
    match = re.search(r'\d+', item_id)
    if match:
        return int(match.group())
    return 0


def _extract_scaffold_seq(item_id: str) -> tuple:
    """
    从支架问题 ID 中提取排序元组。
    三段式：S1-1-1 -> (1, 1, 1)  两段式：S1-2 -> (1, 2, 0)
    """
    match3 = re.match(r'S(\d+)-(\d+)-(\d+)', item_id)
    if match3:
        return (int(match3.group(1)), int(match3.group(2)), int(match3.group(3)))
    match2 = re.match(r'S(\d+)-(\d+)', item_id)
    if match2:
        return (int(match2.group(1)), int(match2.group(2)), 0)
    match1 = re.search(r'(\d+)', item_id)
    if match1:
        return (int(match1.group(1)), 0, 0)
    return (999, 999, 0)
