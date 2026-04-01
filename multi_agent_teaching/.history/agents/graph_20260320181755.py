"""LangGraph workflow — orchestrates all generation and validation agents."""

from langgraph.graph import StateGraph, END

from agents.state import GraphState
from agents.generators.learning_analysis import learning_analysis_node
from agents.generators.teaching_logic_design import teaching_logic_design_node
from agents.generators.main_question_chain import main_question_chain_node
from agents.generators.variant_question import variant_question_node
from agents.generators.scaffold_question import scaffold_question_node
from agents.generators.map_integration import map_integration_node
from agents.validators.cognitive_alignment import cognitive_alignment_node
from agents.validators.goal_alignment import goal_alignment_node
from agents.validators.learning_alignment import learning_alignment_node
from agents.validators.logic_alignment import logic_alignment_node
from config import MAX_VALIDATION_RETRIES


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------

def after_cognitive_check(state: dict) -> str:
    for vr in state.get("validation_results", []):
        if vr.get("validator") == "cognitive_alignment" and not vr.get("passed"):
            retry = state.get("main_retry_count", 0)
            if retry < MAX_VALIDATION_RETRIES:
                return "retry_main"
    return "continue"


def after_goal_check(state: dict) -> str:
    for vr in state.get("validation_results", []):
        if vr.get("validator") == "goal_alignment" and not vr.get("passed"):
            retry = state.get("main_retry_count", 0)
            if retry < MAX_VALIDATION_RETRIES:
                return "retry_main"
    return "continue"


def after_learning_check(state: dict) -> str:
    for vr in state.get("validation_results", []):
        if vr.get("validator") == "learning_alignment" and not vr.get("passed"):
            retry = state.get("scaffold_retry_count", 0)
            if retry < MAX_VALIDATION_RETRIES:
                return "retry_scaffold"
    return "continue"


def after_logic_check(state: dict) -> str:
    for vr in state.get("validation_results", []):
        if vr.get("validator") == "logic_alignment" and not vr.get("passed"):
            # 逻辑校验失败会走“重新生成支架问题”的路径，
            # 因此应使用 scaffold_retry_count 来限制重试次数，
            # 否则 logic_retry_count 永远不递增会导致无限循环。
            retry = state.get("scaffold_retry_count", 0)
            if retry < MAX_VALIDATION_RETRIES:
                return "retry_scaffold"
    return "continue"


# ---------------------------------------------------------------------------
# Retry counter bump nodes
# ---------------------------------------------------------------------------

def bump_main_retry(state: dict) -> dict:
    return {
        "main_retry_count": state.get("main_retry_count", 0) + 1,
        "progress_messages": [
            "[系统] 主干问题校验未通过，第 %d 次重新生成" % (state.get("main_retry_count", 0) + 1)
        ],
    }


def bump_scaffold_retry(state: dict) -> dict:
    return {
        "scaffold_retry_count": state.get("scaffold_retry_count", 0) + 1,
        "progress_messages": [
            "[系统] 支架/逻辑校验未通过，第 %d 次重新生成" % (state.get("scaffold_retry_count", 0) + 1)
        ],
    }


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    workflow = StateGraph(GraphState)

    # --- Add nodes ---
    workflow.add_node("learning_analysis", learning_analysis_node)
    workflow.add_node("teaching_logic_design", teaching_logic_design_node)
    workflow.add_node("main_question_chain", main_question_chain_node)
    workflow.add_node("cognitive_check", cognitive_alignment_node)
    workflow.add_node("goal_check", goal_alignment_node)
    workflow.add_node("variant_question", variant_question_node)
    workflow.add_node("scaffold_question", scaffold_question_node)
    workflow.add_node("learning_check", learning_alignment_node)
    workflow.add_node("logic_check", logic_alignment_node)
    workflow.add_node("map_integration", map_integration_node)
    workflow.add_node("bump_main_retry", bump_main_retry)
    workflow.add_node("bump_scaffold_retry", bump_scaffold_retry)

    # --- Entry point ---
    workflow.set_entry_point("learning_analysis")

    # --- Linear edges: analysis → logic design → main chain ---
    workflow.add_edge("learning_analysis", "teaching_logic_design")
    workflow.add_edge("teaching_logic_design", "main_question_chain")
    workflow.add_edge("main_question_chain", "cognitive_check")

    # --- Cognitive check → goal check or retry ---
    workflow.add_conditional_edges(
        "cognitive_check",
        after_cognitive_check,
        {"retry_main": "bump_main_retry", "continue": "goal_check"},
    )
    workflow.add_edge("bump_main_retry", "main_question_chain")

    # --- Goal check → variant generation or retry ---
    workflow.add_conditional_edges(
        "goal_check",
        after_goal_check,
        {"retry_main": "bump_main_retry", "continue": "variant_question"},
    )

    # --- Variant → scaffold ---
    workflow.add_edge("variant_question", "scaffold_question")

    # --- Scaffold → learning check ---
    workflow.add_edge("scaffold_question", "learning_check")

    # --- Learning check → logic check or retry scaffold ---
    workflow.add_conditional_edges(
        "learning_check",
        after_learning_check,
        {"retry_scaffold": "bump_scaffold_retry", "continue": "logic_check"},
    )
    workflow.add_edge("bump_scaffold_retry", "scaffold_question")

    # --- Logic check → map integration or retry scaffold ---
    workflow.add_conditional_edges(
        "logic_check",
        after_logic_check,
        {"retry_scaffold": "bump_scaffold_retry", "continue": "map_integration"},
    )

    # --- End ---
    workflow.add_edge("map_integration", END)

    return workflow.compile()
