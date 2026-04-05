"""LangGraph workflow — orchestrates all generation and validation agents."""

from langgraph.graph import StateGraph, END

from agents.state import GraphState
from agents.generators.learning_analysis import learning_analysis_node
from agents.generators.teaching_logic_design import teaching_logic_design_node
from agents.generators.main_question_chain import main_question_chain_node
from agents.generators.variant_question import variant_question_node
from agents.generators.scaffold_question import scaffold_question_node
from agents.generators.map_integration import map_integration_node
from agents.validators.integrated_main_question_validator import integrated_main_question_validator_node
from agents.validators.variant_alignment import variant_alignment_node
from agents.validators.scaffold_alignment import scaffold_alignment_node
from config import MAX_VALIDATION_RETRIES


MAIN_VALIDATOR_NAME = "integrated_main_question_validator"


def _feedback_item_target(item) -> str:
    if not isinstance(item, dict):
        return str(item)
    return str(
        item.get("id")
        or item.get("question_id")
        or item.get("target_node")
        or item.get("target")
        or item.get("dimension")
        or ""
    )


# ---------------------------------------------------------------------------
# Main check node (single integrated validator)
# ---------------------------------------------------------------------------

def main_question_check_node(state: dict) -> dict:
    return integrated_main_question_validator_node(state)


def route_after_main_check(state: dict) -> str:
    for vr in state.get("validation_results", []):
        if vr.get("validator") == MAIN_VALIDATOR_NAME:
            if not vr.get("passed", True):
                if state.get("main_retry_count", 0) < MAX_VALIDATION_RETRIES:
                    return "retry_main"
    return "continue"


def bump_main_retry(state: dict) -> dict:
    new_count = state.get("main_retry_count", 0) + 1

    saved_feedback = [
        vr for vr in state.get("validation_results", [])
        if vr.get("validator") == MAIN_VALIDATOR_NAME
    ]

    feedback_info = ""
    for vr in saved_feedback:
        if not vr.get("passed"):
            must_fix = vr.get("feedback", {}).get("must_fix", [])
            if must_fix:
                targets = [_feedback_item_target(m) for m in must_fix[:3]]
                targets = [t for t in targets if t]
                if targets:
                    feedback_info = " — 需修复: %s" % ", ".join(targets)
            break

    return {
        "main_retry_count": new_count,
        "validation_results": [],
        "main_validation_feedback": saved_feedback,
        "progress_messages": ["[系统] 主干问题检验未通过，第 %d 次重新生成%s" % (new_count, feedback_info)],
    }


# ---------------------------------------------------------------------------
# Variant pipeline: generate → check → route
# ---------------------------------------------------------------------------

def variant_check_node(state: dict) -> dict:
    return variant_alignment_node(state)


def route_after_variant_check(state: dict) -> str:
    for vr in state.get("validation_results", []):
        if vr.get("validator") == "variant_alignment" and not vr.get("passed", True):
            if state.get("variant_retry_count", 0) < MAX_VALIDATION_RETRIES:
                return "retry_variant"
    return "done_variant"


def mark_variant_done(state: dict) -> dict:
    passed = all(
        vr.get("passed", True)
        for vr in state.get("validation_results", [])
        if vr.get("validator") == "variant_alignment"
    )
    retry = state.get("variant_retry_count", 0)
    if passed:
        msg = "[系统] 变式问题检验通过" + ("（经 %d 次重试）" % retry if retry > 0 else "")
    else:
        msg = "[系统] 变式问题检验未通过，已达最大重试次数（%d 次），使用当前结果继续" % retry
    return {"sub_pipelines_done": 1, "progress_messages": [msg]}


def bump_variant_retry(state: dict) -> dict:
    new_count = state.get("variant_retry_count", 0) + 1

    saved_feedback = [
        vr for vr in state.get("validation_results", [])
        if vr.get("validator") == "variant_alignment"
    ]

    feedback_info = ""
    for vr in saved_feedback:
        if not vr.get("passed"):
            must_fix = vr.get("feedback", {}).get("must_fix", [])
            if must_fix:
                targets = [_feedback_item_target(m) for m in must_fix[:3]]
                targets = [t for t in targets if t]
                if targets:
                    feedback_info = " — 需修复: %s" % ", ".join(targets)
            break

    return {
        "variant_retry_count": new_count,
        "validation_results": [],
        "variant_validation_feedback": saved_feedback,
        "progress_messages": ["[系统] 变式问题检验未通过，第 %d 次重新生成%s" % (new_count, feedback_info)],
    }


# ---------------------------------------------------------------------------
# Scaffold pipeline: generate → check → route
# ---------------------------------------------------------------------------

def scaffold_check_node(state: dict) -> dict:
    return scaffold_alignment_node(state)


def route_after_scaffold_check(state: dict) -> str:
    for vr in state.get("validation_results", []):
        if vr.get("validator") == "scaffold_alignment" and not vr.get("passed", True):
            if state.get("scaffold_retry_count", 0) < MAX_VALIDATION_RETRIES:
                return "retry_scaffold"
    return "done_scaffold"


def mark_scaffold_done(state: dict) -> dict:
    passed = all(
        vr.get("passed", True)
        for vr in state.get("validation_results", [])
        if vr.get("validator") == "scaffold_alignment"
    )
    retry = state.get("scaffold_retry_count", 0)
    if passed:
        msg = "[系统] 支架问题检验通过" + ("（经 %d 次重试）" % retry if retry > 0 else "")
    else:
        msg = "[系统] 支架问题检验未通过，已达最大重试次数（%d 次），使用当前结果继续" % retry
    return {"sub_pipelines_done": 1, "progress_messages": [msg]}


def bump_scaffold_retry(state: dict) -> dict:
    new_count = state.get("scaffold_retry_count", 0) + 1

    saved_feedback = [
        vr for vr in state.get("validation_results", [])
        if vr.get("validator") == "scaffold_alignment"
    ]

    feedback_info = ""
    for vr in saved_feedback:
        if not vr.get("passed"):
            must_fix = vr.get("feedback", {}).get("must_fix", [])
            if must_fix:
                targets = [_feedback_item_target(m) for m in must_fix[:3]]
                targets = [t for t in targets if t]
                if targets:
                    feedback_info = " — 需修复: %s" % ", ".join(targets)
            break

    return {
        "scaffold_retry_count": new_count,
        "validation_results": [],
        "scaffold_validation_feedback": saved_feedback,
        "progress_messages": ["[系统] 支架问题检验未通过，第 %d 次重新生成%s" % (new_count, feedback_info)],
    }


# ---------------------------------------------------------------------------
# Wait for both variant+scaffold to finish before map_integration
# ---------------------------------------------------------------------------

REQUIRED_SUB_PIPELINES = 2

def aggregate_sub_pipelines(state: dict) -> dict:
    done = state.get("sub_pipelines_done", 0)
    if done >= REQUIRED_SUB_PIPELINES:
        return {
            "sub_pipelines_done": -999,
            "progress_messages": [
                "[系统] 变式问题与支架问题流水线均已完成，开始整合教学地图..."
            ],
        }
    return {}


def route_after_sub_aggregate(state: dict) -> str:
    done = state.get("sub_pipelines_done", 0)
    if done >= REQUIRED_SUB_PIPELINES or done <= 0:
        return "do_integration"
    return "wait_more"


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    workflow = StateGraph(GraphState)

    # --- Generator nodes ---
    workflow.add_node("learning_analysis", learning_analysis_node)
    workflow.add_node("teaching_logic_design", teaching_logic_design_node)
    workflow.add_node("main_question_chain", main_question_chain_node)
    workflow.add_node("variant_question", variant_question_node)
    workflow.add_node("scaffold_question", scaffold_question_node)
    workflow.add_node("aggregate_sub_pipelines", aggregate_sub_pipelines)
    workflow.add_node("map_integration", map_integration_node)

    # --- Main check node (single integrated validator) ---
    workflow.add_node("main_question_check", main_question_check_node)
    workflow.add_node("bump_main_retry", bump_main_retry)

    # --- Variant pipeline nodes ---
    workflow.add_node("variant_check", variant_check_node)
    workflow.add_node("bump_variant_retry", bump_variant_retry)
    workflow.add_node("mark_variant_done", mark_variant_done)

    # --- Scaffold pipeline nodes ---
    workflow.add_node("scaffold_check", scaffold_check_node)
    workflow.add_node("bump_scaffold_retry", bump_scaffold_retry)
    workflow.add_node("mark_scaffold_done", mark_scaffold_done)

    # --- Entry ---
    workflow.set_entry_point("learning_analysis")

    # === Phase 1: 学情分析 → 蓝图 → 主干生成 ===
    workflow.add_edge("learning_analysis", "teaching_logic_design")
    workflow.add_edge("teaching_logic_design", "main_question_chain")

    # === Phase 2: 主干问题综合检验（单一校验节点） ===
    workflow.add_edge("main_question_chain", "main_question_check")

    workflow.add_conditional_edges(
        "main_question_check",
        route_after_main_check,
        {"retry_main": "bump_main_retry", "continue": "fan_out_gen"},
    )

    def _fan_out_gen_node(state: dict) -> dict:
        retry = state.get("main_retry_count", 0)
        if retry >= MAX_VALIDATION_RETRIES:
            msg = "[系统] 主干检验未完全通过，已达最大重试次数，使用当前结果继续。并行生成变式与支架问题..."
        else:
            msg = "[系统] 主干检验通过，并行生成变式与支架问题..."
        return {"progress_messages": [msg]}
    workflow.add_node("fan_out_gen", _fan_out_gen_node)
    workflow.add_edge("fan_out_gen", "variant_question")
    workflow.add_edge("fan_out_gen", "scaffold_question")

    # 主干重试固定回到主干问题生成
    workflow.add_edge("bump_main_retry", "main_question_chain")

    # === Phase 3: 变式/支架独立流水线 ===
    workflow.add_edge("variant_question", "variant_check")
    workflow.add_conditional_edges(
        "variant_check",
        route_after_variant_check,
        {"retry_variant": "bump_variant_retry", "done_variant": "mark_variant_done"},
    )
    workflow.add_edge("bump_variant_retry", "variant_question")
    workflow.add_edge("mark_variant_done", "aggregate_sub_pipelines")

    workflow.add_edge("scaffold_question", "scaffold_check")
    workflow.add_conditional_edges(
        "scaffold_check",
        route_after_scaffold_check,
        {"retry_scaffold": "bump_scaffold_retry", "done_scaffold": "mark_scaffold_done"},
    )
    workflow.add_edge("bump_scaffold_retry", "scaffold_question")
    workflow.add_edge("mark_scaffold_done", "aggregate_sub_pipelines")

    # === Phase 4: 计数器门控 fan-in → 地图整合 ===
    workflow.add_conditional_edges(
        "aggregate_sub_pipelines",
        route_after_sub_aggregate,
        {"do_integration": "map_integration", "wait_more": END},
    )
    workflow.add_edge("map_integration", END)

    return workflow.compile()
