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
from agents.validators.learning_alignment import learning_alignment_node
from config import MAX_VALIDATION_RETRIES


# ---------------------------------------------------------------------------
# Fan-out: dispatch parallel validator branches
# ---------------------------------------------------------------------------

def fan_out_main_checks(state: dict):
    """主干问题生成后，同时派发三个并行检验分支"""
    return [
        Send("cognitive_check", state),
        Send("goal_check", state),
        Send("teaching_logic_check", state),
    ]


def fan_out_variant_scaffold_checks(state: dict):
    """支架问题生成后，派发学情对齐检验分支"""
    return [
        Send("learning_check", state),
    ]


# ---------------------------------------------------------------------------
# Validator wrapper nodes — each also increments the fan-in counter
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


def learning_check_node(state: dict) -> dict:
    result = learning_alignment_node(state)
    result["variant_scaffold_checks_done"] = 1
    return result


# ---------------------------------------------------------------------------
# Fan-in: collect results and route
# ---------------------------------------------------------------------------

def aggregate_main_checks(state: dict) -> dict:
    """扇入节点：汇总三项并行检验结果，生成摘要消息"""
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


def aggregate_variant_scaffold_checks(state: dict) -> dict:
    """扇入节点：汇总学情对齐检验结果，生成摘要消息"""
    results = state.get("validation_results", [])
    passed_all = all(
        vr.get("passed", True)
        for vr in results
        if vr.get("validator") == "learning_alignment"
    )
    status = "通过" if passed_all else "未通过"
    return {
        "variant_scaffold_checks_done": -999,
        "progress_messages": ["[系统] 变式/支架学情检验完成（%s）" % status],
    }


# ---------------------------------------------------------------------------
# Routing after aggregation
# ---------------------------------------------------------------------------

def route_after_main_checks(state: dict) -> str:
    """汇总后判断主干问题检验结果，任意一个未通过则重试"""
    for vr in state.get("validation_results", []):
        if vr.get("validator") in ("cognitive_alignment", "goal_alignment", "teaching_logic_alignment"):
            if not vr.get("passed", True):
                retry = state.get("main_retry_count", 0)
                if retry < MAX_VALIDATION_RETRIES:
                    return "retry_main"
    return "continue"


def route_after_variant_scaffold_checks(state: dict) -> str:
    """汇总后判断变式/支架检验结果"""
    for vr in state.get("validation_results", []):
        if vr.get("validator") == "learning_alignment" and not vr.get("passed", True):
            retry_target = vr.get("retry_target", "scaffold")
            if retry_target == "variant":
                retry = state.get("variant_retry_count", 0)
                if retry < MAX_VALIDATION_RETRIES:
                    return "retry_variant"
            else:
                retry = state.get("scaffold_retry_count", 0)
                if retry < MAX_VALIDATION_RETRIES:
                    return "retry_scaffold"
    return "continue"


# ---------------------------------------------------------------------------
# Retry counter bump nodes
# ---------------------------------------------------------------------------

def _safe_join_issue_ids(items: list, key: str) -> str:
    values = []
    for item in items[:3]:
        if not isinstance(item, dict):
            continue
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            values.append(text)
    return ", ".join(values)

def bump_main_retry(state: dict) -> dict:
    new_count = state.get("main_retry_count", 0) + 1
    feedback_info = ""
    for vr in state.get("validation_results", []):
        if vr.get("validator") in ("cognitive_alignment", "goal_alignment", "teaching_logic_alignment") and not vr.get("passed"):
            feedback = vr.get("feedback", {})
            must_fix = feedback.get("must_fix", [])
            if must_fix:
                ids = _safe_join_issue_ids(must_fix, "node_id")
                if ids:
                    feedback_info = " — 需修复: %s" % ids
                break
    return {
        "main_retry_count": new_count,
        "validation_results": [],
        "progress_messages": [
            "[系统] 主干问题检验未通过，第 %d 次重新生成%s" % (new_count, feedback_info)
        ],
    }


def bump_variant_retry(state: dict) -> dict:
    new_count = state.get("variant_retry_count", 0) + 1
    feedback_info = ""
    for vr in state.get("validation_results", []):
        if vr.get("validator") == "learning_alignment" and not vr.get("passed"):
            feedback = vr.get("feedback", {})
            must_fix = feedback.get("must_fix_variant", [])
            if must_fix:
                ids = _safe_join_issue_ids(must_fix, "question_id")
                if ids:
                    feedback_info = " — 需修复: %s" % ids
            break
    return {
        "variant_retry_count": new_count,
        "validation_results": [],
        "progress_messages": [
            "[系统] 变式问题检验未通过，第 %d 次重新生成%s" % (new_count, feedback_info)
        ],
    }


def bump_scaffold_retry(state: dict) -> dict:
    new_count = state.get("scaffold_retry_count", 0) + 1
    feedback_info = ""
    for vr in state.get("validation_results", []):
        if vr.get("validator") == "learning_alignment" and not vr.get("passed"):
            feedback = vr.get("feedback", {})
            must_fix = feedback.get("must_fix_scaffold", [])
            if must_fix:
                ids = _safe_join_issue_ids(must_fix, "question_id")
                if ids:
                    feedback_info = " — 需修复: %s" % ids
            break
    return {
        "scaffold_retry_count": new_count,
        "validation_results": [],
        "progress_messages": [
            "[系统] 支架问题检验未通过，第 %d 次重新生成%s" % (new_count, feedback_info)
        ],
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
    workflow.add_node("map_integration", map_integration_node)

    # --- Parallel validator nodes (wrapped) ---
    workflow.add_node("cognitive_check", cognitive_check_node)
    workflow.add_node("goal_check", goal_check_node)
    workflow.add_node("teaching_logic_check", teaching_logic_check_node)
    workflow.add_node("learning_check", learning_check_node)

    # --- Fan-in aggregation nodes ---
    workflow.add_node("aggregate_main_checks", aggregate_main_checks)
    workflow.add_node("aggregate_variant_scaffold_checks", aggregate_variant_scaffold_checks)

    # --- Retry bump nodes ---
    workflow.add_node("bump_main_retry", bump_main_retry)
    workflow.add_node("bump_variant_retry", bump_variant_retry)
    workflow.add_node("bump_scaffold_retry", bump_scaffold_retry)

    # --- Entry point ---
    workflow.set_entry_point("learning_analysis")

    # --- Linear: analysis → logic design → main chain ---
    workflow.add_edge("learning_analysis", "teaching_logic_design")
    workflow.add_edge("teaching_logic_design", "main_question_chain")

    # --- Fan-out: main chain → 3 parallel checks ---
    workflow.add_conditional_edges(
        "main_question_chain",
        fan_out_main_checks,
        ["cognitive_check", "goal_check", "teaching_logic_check"],
    )

    # --- All 3 checks fan-in to aggregate node ---
    workflow.add_edge("cognitive_check", "aggregate_main_checks")
    workflow.add_edge("goal_check", "aggregate_main_checks")
    workflow.add_edge("teaching_logic_check", "aggregate_main_checks")

    # --- Route after aggregation ---
    workflow.add_conditional_edges(
        "aggregate_main_checks",
        route_after_main_checks,
        {"retry_main": "bump_main_retry", "continue": "variant_question"},
    )
    workflow.add_edge("bump_main_retry", "main_question_chain")

    # --- Variant → scaffold ---
    workflow.add_edge("variant_question", "scaffold_question")

    # --- Fan-out: scaffold → learning check ---
    workflow.add_conditional_edges(
        "scaffold_question",
        fan_out_variant_scaffold_checks,
        ["learning_check"],
    )

    # --- learning check → aggregate node ---
    workflow.add_edge("learning_check", "aggregate_variant_scaffold_checks")

    # --- Route after aggregation ---
    workflow.add_conditional_edges(
        "aggregate_variant_scaffold_checks",
        route_after_variant_scaffold_checks,
        {
            "retry_variant": "bump_variant_retry",
            "retry_scaffold": "bump_scaffold_retry",
            "continue": "map_integration",
        },
    )
    workflow.add_edge("bump_variant_retry", "variant_question")
    workflow.add_edge("bump_scaffold_retry", "scaffold_question")

    # --- End ---
    workflow.add_edge("map_integration", END)

    return workflow.compile()
