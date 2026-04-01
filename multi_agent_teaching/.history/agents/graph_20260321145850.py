"""LangGraph workflow — orchestrates all generation and validation agents."""

from langgraph.graph import StateGraph, END
from langgraph.types import Send

from agents.state import GraphState
from agents.generators.learning_analysis import learning_analysis_node
from agents.generators.teaching_logic_design import teaching_logic_design_node
from agents.generators.main_question_chain import main_question_chain_node
from agents.generators.variant_question import variant_question_node
from agents.generators.scaffold_question import scaffold_question_node
from agents.generators.map_integration import map_integration_node
from agents.validators.cognitive_alignment import cognitive_alignment_node
from agents.validators.goal_alignment import goal_alignment_node
from agents.validators.teaching_logic_alignment import teaching_logic_alignment_node
from agents.validators.variant_alignment import variant_alignment_node
from agents.validators.scaffold_alignment import scaffold_alignment_node
from config import MAX_VALIDATION_RETRIES


# ---------------------------------------------------------------------------
# Fan-out helpers
# ---------------------------------------------------------------------------

def fan_out_main_checks(state: dict):
    """主干问题生成后，同时派发三个并行检验分支"""
    return [
        Send("cognitive_check", state),
        Send("goal_check", state),
        Send("teaching_logic_check", state),
    ]




# ---------------------------------------------------------------------------
# Main check wrapper nodes (increment fan-in counter)
# ---------------------------------------------------------------------------

def cognitive_check_node(state: dict) -> dict:
    result = cognitive_alignment_node(state)
    result["main_checks_done"] = 1
    return result


def goal_check_node(state: dict) -> dict:
    result = goal_alignment_node(state)
    result["main_checks_done"] = 1
    return result


def teaching_logic_check_node(state: dict) -> dict:
    result = teaching_logic_alignment_node(state)
    result["main_checks_done"] = 1
    return result


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


def bump_variant_retry(state: dict) -> dict:
    new_count = state.get("variant_retry_count", 0) + 1

    # 保留本轮变式检验结果，供变式生成器下一轮读取
    saved_feedback = [
        vr for vr in state.get("validation_results", [])
        if vr.get("validator") == "variant_alignment"
    ]

    feedback_info = ""
    for vr in saved_feedback:
        if not vr.get("passed"):
            must_fix = vr.get("feedback", {}).get("must_fix", [])
            if must_fix:
                feedback_info = " — 需修复: %s" % ", ".join([str(m.get("question_id", "")) if isinstance(m, dict) else str(m) for m in must_fix[:3]])
            break

    # 全清空 validation_results（scaffold 的检验结果在 scaffold_check 重新运行时会写回）
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


def bump_scaffold_retry(state: dict) -> dict:
    new_count = state.get("scaffold_retry_count", 0) + 1

    # 保留本轮支架检验结果，供支架生成器下一轮读取
    saved_feedback = [
        vr for vr in state.get("validation_results", [])
        if vr.get("validator") == "scaffold_alignment"
    ]

    feedback_info = ""
    for vr in saved_feedback:
        if not vr.get("passed"):
            must_fix = vr.get("feedback", {}).get("must_fix", [])
            if must_fix:
                feedback_info = " — 需修复: %s" % ", ".join([str(m.get("question_id", "")) if isinstance(m, dict) else str(m) for m in must_fix[:3]])
            break

    # 全清空 validation_results（variant 的检验结果在 variant_check 重新运行时会写回）
    return {
        "scaffold_retry_count": new_count,
        "validation_results": [],
        "scaffold_validation_feedback": saved_feedback,
        "progress_messages": ["[系统] 支架问题检验未通过，第 %d 次重新生成%s" % (new_count, feedback_info)],
    }


# ---------------------------------------------------------------------------
# Main checks fan-in
# ---------------------------------------------------------------------------

def aggregate_main_checks(state: dict) -> dict:
    results = state.get("validation_results", [])
    passed_all = all(
        vr.get("passed", True)
        for vr in results
        if vr.get("validator") in ("cognitive_alignment", "goal_alignment", "teaching_logic_alignment")
    )
    status = "全部通过" if passed_all else "存在未通过项"
    return {
        "main_checks_done": -999,
        "progress_messages": ["[系统] 主干问题三项并行检验完成（%s）" % status],
    }


def route_after_main_checks(state: dict) -> str:
    for vr in state.get("validation_results", []):
        if vr.get("validator") in ("cognitive_alignment", "goal_alignment", "teaching_logic_alignment"):
            if not vr.get("passed", True):
                if state.get("main_retry_count", 0) < MAX_VALIDATION_RETRIES:
                    return "retry_main"
    return "continue"


def bump_main_retry(state: dict) -> dict:
    new_count = state.get("main_retry_count", 0) + 1
    main_validators = ("cognitive_alignment", "goal_alignment", "teaching_logic_alignment")

    # 保留本轮三个验证器的结果，供主干生成器下一轮读取
    saved_feedback = [
        vr for vr in state.get("validation_results", [])
        if vr.get("validator") in main_validators
    ]

    feedback_info = ""
    for vr in saved_feedback:
        if not vr.get("passed"):
            must_fix = vr.get("feedback", {}).get("must_fix", [])
            if must_fix:
                feedback_info = " — 需修复: %s" % ", ".join([str(m.get("node_id", "")) if isinstance(m, dict) else str(m) for m in must_fix[:3]])
                break

    return {
        "main_retry_count": new_count,
        "validation_results": [],
        "main_validation_feedback": saved_feedback,
        "progress_messages": ["[系统] 主干问题检验未通过，第 %d 次重新生成%s" % (new_count, feedback_info)],
    }




# ---------------------------------------------------------------------------
# Wait for both variant+scaffold to finish before map_integration
# ---------------------------------------------------------------------------

def wait_for_both(state: dict) -> dict:
    """两条流水线均完成后，LangGraph fan-in 触发此节点一次，然后进行地图整合"""
    return {
        "progress_messages": ["[系统] 变式与支架问题均已完成，开始整合教学地图..."],
    }


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
    workflow.add_node("wait_for_both", wait_for_both)
    workflow.add_node("map_integration", map_integration_node)

    # --- Main check nodes ---
    workflow.add_node("cognitive_check", cognitive_check_node)
    workflow.add_node("goal_check", goal_check_node)
    workflow.add_node("teaching_logic_check", teaching_logic_check_node)
    workflow.add_node("aggregate_main_checks", aggregate_main_checks)
    workflow.add_node("bump_main_retry", bump_main_retry)

    # --- Variant pipeline nodes ---
    workflow.add_node("variant_check", variant_check_node)
    workflow.add_node("bump_variant_retry", bump_variant_retry)

    # --- Scaffold pipeline nodes ---
    workflow.add_node("scaffold_check", scaffold_check_node)
    workflow.add_node("bump_scaffold_retry", bump_scaffold_retry)

    # --- Entry ---
    workflow.set_entry_point("learning_analysis")

    # === Phase 1: 学情分析 → 蓝图 → 主干生成 ===
    workflow.add_edge("learning_analysis", "teaching_logic_design")
    workflow.add_edge("teaching_logic_design", "main_question_chain")

    # === Phase 2: 主干问题并行检验 ===
    workflow.add_conditional_edges(
        "main_question_chain",
        fan_out_main_checks,
        ["cognitive_check", "goal_check", "teaching_logic_check"],
    )
    workflow.add_edge("cognitive_check", "aggregate_main_checks")
    workflow.add_edge("goal_check", "aggregate_main_checks")
    workflow.add_edge("teaching_logic_check", "aggregate_main_checks")

    workflow.add_conditional_edges(
        "aggregate_main_checks",
        route_after_main_checks,
        {"retry_main": "bump_main_retry", "continue": "fan_out_gen"},
    )
    workflow.add_node("fan_out_gen", lambda state: {"progress_messages": ["[系统] 主干检验通过，并行生成变式与支架问题..."]})
    # fan_out_gen 用普通双出边连接两个生成节点，LangGraph 会并行执行并在 wait_for_both 统一 fan-in
    workflow.add_edge("fan_out_gen", "variant_question")
    workflow.add_edge("fan_out_gen", "scaffold_question")
    workflow.add_edge("bump_main_retry", "main_question_chain")

    # === Phase 3: 变式/支架独立流水线（各自生成 → 检验 → 重试/通过 → fan-in）===
    workflow.add_edge("variant_question", "variant_check")
    workflow.add_conditional_edges(
        "variant_check",
        route_after_variant_check,
        {"retry_variant": "bump_variant_retry", "done_variant": "wait_for_both"},
    )
    workflow.add_edge("bump_variant_retry", "variant_question")

    workflow.add_edge("scaffold_question", "scaffold_check")
    workflow.add_conditional_edges(
        "scaffold_check",
        route_after_scaffold_check,
        {"retry_scaffold": "bump_scaffold_retry", "done_scaffold": "wait_for_both"},
    )
    workflow.add_edge("bump_scaffold_retry", "scaffold_question")

    # === Phase 4: 两条流水线 fan-in 到 wait_for_both → 地图整合 ===
    # wait_for_both 有两条入边（variant_check 和 scaffold_check 的 continue 出口），
    # LangGraph 在同一 superstep 中收到两条入边后才触发一次
    workflow.add_edge("wait_for_both", "map_integration")
    workflow.add_edge("map_integration", END)

    return workflow.compile()
