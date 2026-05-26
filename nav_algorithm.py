"""Teaching Map Navigation Algorithm

Implements the dispatch logic described in algorithm.md:
Given current node, participation level, accuracy level, and visited history,
determine the next question node to display.
"""

import re
from typing import Dict, List, Optional


def dispatch_next(
    teaching_map: dict,
    current_node_id: str,
    participation: str,
    accuracy: str,
    visited: List[str],
) -> dict:
    """Determine the next question to dispatch based on real-time classroom state.

    Args:
        teaching_map: {nodes: [...], edges: [...]}
        current_node_id: ID of the currently displayed question
        participation: "high" or "low"
        accuracy: "high" or "low"
        visited: list of already-visited node IDs

    Returns:
        {
            "next_node_id": str or None,
            "show_explanation": bool,
            "explanation_node_id": str or None,
            "completed": bool,
        }
    """
    nodes = teaching_map.get("nodes", [])
    edges = teaching_map.get("edges", [])

    if not nodes or not current_node_id:
        return _result(None, False, None, True)

    index = _build_index(nodes, edges)
    current_node = index["node_map"].get(current_node_id)
    if not current_node:
        return _result(None, False, None, True)

    current_type = current_node.get("question_type", "main")
    current_unit_id = _get_unit_id(current_node, index)

    # Scaffold-chain lock: while inside a scaffold chain, always advance sequentially.
    # Only when the current node is the last in its chain do we fall through to scenario logic.
    if current_type == "scaffold":
        next_in_chain = _next_in_scaffold_chain(current_node_id, current_node, index, visited)
        if next_in_chain is not None:
            return _result(next_in_chain, False, None)
        # current node is the last (or only) scaffold in its chain — use scenario exit logic

    if participation == "high" and accuracy == "high":
        res = _scenario_high_high(current_node_id, current_type, current_unit_id, index, visited)
    elif participation == "high" and accuracy == "low":
        res = _scenario_high_low(current_node_id, current_type, current_unit_id, index, visited)
    elif participation == "low" and accuracy == "high":
        res = _scenario_low_high(current_node_id, current_type, current_unit_id, index, visited)
    else:
        res = _scenario_low_low(current_node_id, current_type, current_unit_id, index, visited)

    # Chain-entry normalisation: if any scenario dispatches to a scaffold that is not
    # the first in its chain, redirect to the actual first unvisited node in that chain.
    next_id = res.get("next_node_id")
    if next_id and not res.get("completed"):
        next_node = index["node_map"].get(next_id)
        if next_node and next_node.get("question_type") == "scaffold":
            corrected = _chain_entry_node(next_id, next_node, index, visited)
            if corrected != next_id:
                res = dict(res, next_node_id=corrected)

    return res


def _result(next_node_id: Optional[str], show_explanation: bool,
            explanation_node_id: Optional[str], completed: bool = False) -> dict:
    return {
        "next_node_id": next_node_id,
        "show_explanation": show_explanation,
        "explanation_node_id": explanation_node_id,
        "completed": completed,
    }


def _build_index(nodes: List[dict], edges: List[dict] = ()) -> dict:
    """Build lookup structures for efficient navigation.
    The edges parameter is accepted for compatibility but no longer used for dispatch.
    """
    node_map = {n["id"]: n for n in nodes if n.get("id")}

    main_nodes = sorted(
        [n for n in nodes if n.get("question_type") == "main"],
        key=lambda x: _extract_number(x.get("id", ""))
    )
    main_ids_ordered = [n["id"] for n in main_nodes]

    # Group nodes by teaching unit (keyed by main question ID)
    units: Dict[str, Dict[str, List[dict]]] = {}
    for mid in main_ids_ordered:
        units[mid] = {"main": [node_map[mid]], "variant": [], "scaffold": []}

    for n in nodes:
        qtype = n.get("question_type", "")
        if qtype == "variant":
            parent = n.get("main_id") or n.get("parent_id") or ""
            if parent in units:
                units[parent]["variant"].append(n)
        elif qtype == "scaffold":
            from_id = n.get("from_id") or n.get("from_main_id") or ""
            if from_id in units:
                units[from_id]["scaffold"].append(n)

    return {
        "node_map": node_map,
        "main_ids_ordered": main_ids_ordered,
        "units": units,
    }


def _get_unit_id(node: dict, index: dict) -> str:
    """Determine which teaching unit a node belongs to."""
    qtype = node.get("question_type", "main")
    if qtype == "main":
        return node["id"]
    elif qtype == "variant":
        return node.get("main_id") or node.get("parent_id") or ""
    else:  # scaffold
        return node.get("from_id") or node.get("from_main_id") or ""


def _next_unit_id(current_unit_id: str, index: dict) -> Optional[str]:
    """Get the next teaching unit's main ID in sequence."""
    ordered = index["main_ids_ordered"]
    try:
        idx = ordered.index(current_unit_id)
        if idx + 1 < len(ordered):
            return ordered[idx + 1]
    except ValueError:
        pass
    return None


_TYPE_PRIORITY_DEFAULTS = {"main": 1.0, "variant": 0.8, "scaffold": 0.7}

_TYPE_RANK = {"main": 2, "variant": 1, "scaffold": 0}


def _pick_highest_priority(candidates: List[dict], index: dict, visited: List[str],
                           unvisited_only: bool = False) -> Optional[str]:
    """Pick the candidate node with the highest dispatch priority.

    When candidates contain mixed types (e.g. main + variant), higher-rank types
    that have unvisited nodes are always preferred: unvisited main beats any variant,
    unvisited variant beats any scaffold. Within the same type tier, the node with
    the highest priority wins. Falls back to type-based defaults when a node has no
    priority field. Uses difficulty as tiebreaker when priorities are equal.
    """
    if unvisited_only:
        candidates = [c for c in candidates if c["id"] not in visited]
    if not candidates:
        return None

    has_multiple_types = len({c.get("question_type", "main") for c in candidates}) > 1

    if has_multiple_types:
        unvisited = [c for c in candidates if c["id"] not in visited]
        if unvisited:
            best_rank = max(
                _TYPE_RANK.get(c.get("question_type", "main"), 0) for c in unvisited
            )
            narrowed = [
                c for c in unvisited
                if _TYPE_RANK.get(c.get("question_type", "main"), 0) == best_rank
            ]
            candidates = narrowed
        else:
            best_rank = max(
                _TYPE_RANK.get(c.get("question_type", "main"), 0) for c in candidates
            )
            candidates = [
                c for c in candidates
                if _TYPE_RANK.get(c.get("question_type", "main"), 0) == best_rank
            ]

    if not candidates:
        return None

    def score(node):
        pri = node.get("priority")
        if pri is None:
            pri = _TYPE_PRIORITY_DEFAULTS.get(node.get("question_type", "main"), 0.5)
        difficulty = node.get("difficulty", 0)
        return (pri, difficulty)

    best = max(candidates, key=score)
    return best["id"]


def _get_unit_nodes_by_type(unit_id: str, types: List[str], index: dict) -> List[dict]:
    """Get nodes from a specific unit filtered by question types."""
    unit = index["units"].get(unit_id, {})
    result = []
    for t in types:
        result.extend(unit.get(t, []))
    return result


def _scaffold_sort_key(node: dict) -> tuple:
    """Sort key for scaffolds within a bridge group: use sequence field, then ID numbers."""
    seq = node.get("sequence")
    if isinstance(seq, (int, float)):
        return (int(seq), 0)
    return _extract_scaffold_id_key(node.get("id", ""))


def _extract_scaffold_id_key(node_id: str) -> tuple:
    """Extract sort tuple from scaffold IDs like S1-1-1 (three-segment) or S1-1 (legacy two-segment)."""
    import re as _re
    # Three-segment: S{bridge}-{group}-{seq}
    m3 = _re.match(r'[Ss](\d+)-(\d+)-(\d+)', node_id)
    if m3:
        return (int(m3.group(1)), int(m3.group(2)), int(m3.group(3)))
    # Two-segment legacy: S{bridge}-{seq}
    m2 = _re.match(r'[Ss](\d+)-(\d+)', node_id)
    if m2:
        return (int(m2.group(1)), int(m2.group(2)), 0)
    m1 = _re.search(r'(\d+)', node_id)
    if m1:
        return (int(m1.group(1)), 0, 0)
    return (999, 0, 0)


def _get_chain_key(node: dict) -> str:
    """Get the chain grouping key for a scaffold node.
    Uses bridge_group_id if available, otherwise falls back to from_id|to_id.
    """
    bg = node.get("bridge_group_id", "")
    if bg:
        return bg
    from_id = node.get("from_id") or node.get("from_main_id") or ""
    to_id = node.get("to_id") or node.get("to_main_id") or ""
    return f"{from_id}|{to_id}"


def _get_chain_for_node(node: dict, index: dict) -> List[dict]:
    """Get all scaffold nodes in the same chain as the given node, sorted by sequence."""
    key = _get_chain_key(node)
    chain = [
        n for n in index["node_map"].values()
        if n.get("question_type") == "scaffold" and _get_chain_key(n) == key
    ]
    chain.sort(key=_scaffold_sort_key)
    return chain


def _next_in_scaffold_chain(
    current_id: str,
    current_node: dict,
    index: dict,
    visited: List[str],
) -> Optional[str]:
    """Return the next unvisited scaffold in the same bridge chain, or None if at the end.

    A bridge chain is identified by bridge_group_id (preferred) or (from_id, to_id) fallback.
    """
    chain = _get_chain_for_node(current_node, index)
    if not chain:
        return None

    found_current = False
    for node in chain:
        if found_current:
            if node["id"] not in visited:
                return node["id"]
        if node["id"] == current_id:
            found_current = True

    return None  # current is last (or not found) — exit chain


def _chain_entry_node(
    scaffold_id: str,
    scaffold_node: dict,
    index: dict,
    visited: List[str],
) -> str:
    """When entering a scaffold chain from outside, return the first unvisited node in
    that chain instead of the priority-selected node (which may not be the first).
    Falls back to the original scaffold_id if no better entry is found.
    """
    chain = _get_chain_for_node(scaffold_node, index)
    if not chain:
        return scaffold_id

    for node in chain:
        if node["id"] not in visited:
            return node["id"]

    return scaffold_id  # all visited — let caller handle


def _scaffold_chain_entry_nodes(unit_scaffold_nodes: List[dict], index: dict,
                                visited: List[str]) -> List[dict]:
    """Given all scaffold nodes in a unit, return one representative per bridge group:
    the first unvisited node of each group (keyed by bridge_group_id or from_id|to_id).
    This allows _pick_highest_priority to compare groups by their entry-point priority.
    """
    groups: Dict[str, List[dict]] = {}
    for n in unit_scaffold_nodes:
        key = _get_chain_key(n)
        groups.setdefault(key, []).append(n)

    entries: List[dict] = []
    for chain in groups.values():
        chain.sort(key=_scaffold_sort_key)
        for node in chain:
            if node["id"] not in visited:
                entries.append(node)
                break  # only the first unvisited per group

    return entries


# --- Scenario 1: High participation + High accuracy ---
def _scenario_high_high(current_id: str, current_type: str, unit_id: str,
                        index: dict, visited: List[str]) -> dict:
    """Focus on vertical cognitive advancement."""
    if current_type in ("main", "variant"):
        # Jump to next unit's main/variant with highest priority
        next_unit = _next_unit_id(unit_id, index)
        if not next_unit:
            # Already at the last unit — vertical advancement has nowhere to go
            return _result(None, False, None, True)
        candidates = _get_unit_nodes_by_type(next_unit, ["main", "variant"], index)
        target = _pick_highest_priority(candidates, index, visited)
        if target:
            return _result(target, False, None)
        # Next unit exists but all its nodes are visited — fall back to current unit
        candidates = _get_unit_nodes_by_type(unit_id, ["main", "variant"], index)
        target = _pick_highest_priority(candidates, index, visited, unvisited_only=True)
        if target:
            return _result(target, False, None)
        return _result(None, False, None, True)
    else:  # scaffold
        # Jump to current unit's main/variant with highest priority
        candidates = _get_unit_nodes_by_type(unit_id, ["main", "variant"], index)
        target = _pick_highest_priority(candidates, index, visited)
        if target:
            return _result(target, False, None)
        # Fallback: next unit
        next_unit = _next_unit_id(unit_id, index)
        if next_unit:
            candidates = _get_unit_nodes_by_type(next_unit, ["main", "variant"], index)
            target = _pick_highest_priority(candidates, index, visited)
            if target:
                return _result(target, False, None)
        return _result(None, False, None, True)


# --- Scenario 2: High participation + Low accuracy ---
def _scenario_high_low(current_id: str, current_type: str, unit_id: str,
                       index: dict, visited: List[str]) -> dict:
    """Maintain enthusiasm while fixing cognitive gaps."""
    if current_type in ("main", "variant"):
        # Prioritize unvisited scaffold in current unit — pick by entry-node priority
        candidates = _scaffold_chain_entry_nodes(
            _get_unit_nodes_by_type(unit_id, ["scaffold"], index), index, visited)
        target = _pick_highest_priority(candidates, index, visited)
        if target:
            return _result(target, False, None)
        # No unvisited scaffold: show explanation for current main, then next unit's scaffold
        next_unit = _next_unit_id(unit_id, index)
        if next_unit:
            candidates = _scaffold_chain_entry_nodes(
                _get_unit_nodes_by_type(next_unit, ["scaffold"], index), index, visited)
            target = _pick_highest_priority(candidates, index, visited)
            if target:
                return _result(target, False, None)
        # Fallback: show explanation and try next unit's main/variant
        if next_unit:
            candidates = _get_unit_nodes_by_type(next_unit, ["main", "variant"], index)
            target = _pick_highest_priority(candidates, index, visited)
            if target:
                return _result(target, False, None)
        return _result(None, False, None, True)
    else:  # scaffold
        # Show explanation for current scaffold, then go to current unit's main/variant
        candidates = _get_unit_nodes_by_type(unit_id, ["main", "variant"], index)
        target = _pick_highest_priority(candidates, index, visited)
        if target:
            return _result(target, False, None)
        # Fallback: next unit
        next_unit = _next_unit_id(unit_id, index)
        if next_unit:
            candidates = _get_unit_nodes_by_type(next_unit, ["main", "variant"], index)
            target = _pick_highest_priority(candidates, index, visited)
            if target:
                return _result(target, False, None)
        return _result(None, False, None, True)


# --- Scenario 3: Low participation + High accuracy ---
def _scenario_low_high(current_id: str, current_type: str, unit_id: str,
                       index: dict, visited: List[str]) -> dict:
    """Activate engagement while consolidating cognitive advantage."""
    if current_type in ("main", "variant"):
        # Prioritize unvisited variant in current unit
        candidates = _get_unit_nodes_by_type(unit_id, ["variant"], index)
        target = _pick_highest_priority(candidates, index, visited, unvisited_only=True)
        if target:
            return _result(target, False, None)
        # No unvisited variant: next unit's main/variant
        next_unit = _next_unit_id(unit_id, index)
        if next_unit:
            candidates = _get_unit_nodes_by_type(next_unit, ["main", "variant"], index)
            target = _pick_highest_priority(candidates, index, visited)
            if target:
                return _result(target, False, None)
        # Fallback: any unvisited in current unit (entry-nodes for scaffold groups)
        main_var = _get_unit_nodes_by_type(unit_id, ["main", "variant"], index)
        scaffold_entries = _scaffold_chain_entry_nodes(
            _get_unit_nodes_by_type(unit_id, ["scaffold"], index), index, visited)
        candidates = main_var + scaffold_entries
        target = _pick_highest_priority(candidates, index, visited, unvisited_only=True)
        if target:
            return _result(target, False, None)
        return _result(None, False, None, True)
    else:  # scaffold (chain end — look for another unvisited chain in this unit)
        candidates = _scaffold_chain_entry_nodes(
            _get_unit_nodes_by_type(unit_id, ["scaffold"], index), index, visited)
        target = _pick_highest_priority(candidates, index, visited)
        if target:
            return _result(target, False, None)
        # No unvisited scaffold: current unit's main/variant
        candidates = _get_unit_nodes_by_type(unit_id, ["main", "variant"], index)
        target = _pick_highest_priority(candidates, index, visited)
        if target:
            return _result(target, False, None)
        # Fallback: next unit
        next_unit = _next_unit_id(unit_id, index)
        if next_unit:
            candidates = _get_unit_nodes_by_type(next_unit, ["main", "variant"], index)
            target = _pick_highest_priority(candidates, index, visited)
            if target:
                return _result(target, False, None)
        return _result(None, False, None, True)


# --- Scenario 4: Low participation + Low accuracy ---
def _scenario_low_low(current_id: str, current_type: str, unit_id: str,
                      index: dict, visited: List[str]) -> dict:
    """Fix cognitive issues and activate participation."""
    if current_type in ("main", "variant"):
        # Prioritize unvisited scaffold in current unit — pick by entry-node priority
        candidates = _scaffold_chain_entry_nodes(
            _get_unit_nodes_by_type(unit_id, ["scaffold"], index), index, visited)
        target = _pick_highest_priority(candidates, index, visited)
        if target:
            return _result(target, False, None)
        # No unvisited scaffold: show explanation, then next unit's scaffold
        next_unit = _next_unit_id(unit_id, index)
        if next_unit:
            candidates = _scaffold_chain_entry_nodes(
                _get_unit_nodes_by_type(next_unit, ["scaffold"], index), index, visited)
            target = _pick_highest_priority(candidates, index, visited)
            if target:
                return _result(target, False, None)
        # Fallback: show explanation and try next unit's main
        if next_unit:
            candidates = _get_unit_nodes_by_type(next_unit, ["main", "variant"], index)
            target = _pick_highest_priority(candidates, index, visited)
            if target:
                return _result(target, False, None)
        return _result(None, False, None, True)
    else:  # scaffold (chain end — look for another unvisited chain in this unit)
        candidates = _scaffold_chain_entry_nodes(
            _get_unit_nodes_by_type(unit_id, ["scaffold"], index), index, visited)
        target = _pick_highest_priority(candidates, index, visited)
        if target:
            return _result(target, False, None)
        # No unvisited scaffold: current unit's main/variant
        candidates = _get_unit_nodes_by_type(unit_id, ["main", "variant"], index)
        target = _pick_highest_priority(candidates, index, visited)
        if target:
            return _result(target, False, None)
        # Fallback: next unit
        next_unit = _next_unit_id(unit_id, index)
        if next_unit:
            candidates = _get_unit_nodes_by_type(next_unit, ["main", "variant"], index)
            target = _pick_highest_priority(candidates, index, visited)
            if target:
                return _result(target, False, None)
        return _result(None, False, None, True)


def _extract_number(item_id: str) -> int:
    """Extract the first number from a node ID for sorting (M1 -> 1, M10 -> 10)."""
    match = re.search(r'\d+', item_id)
    return int(match.group()) if match else 0


def get_first_main_node(teaching_map: dict) -> Optional[dict]:
    """Get the first main question node (entry point for navigation)."""
    nodes = teaching_map.get("nodes", [])
    main_nodes = [n for n in nodes if n.get("question_type") == "main"]
    if not main_nodes:
        return None
    main_nodes.sort(key=lambda x: _extract_number(x.get("id", "")))
    return main_nodes[0]
