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
from config import MAX_VALIDATION_RETRIES, MAIN_FULL_RECHECK_INTERVAL


MAIN_VALIDATOR_NODE_MAP = {
    "cognitive_alignment": "cognitive_check",
    "goal_alignment": "goal_check",
    "teaching_logic_alignment": "teaching_logic_check",
}

MAIN_VALIDATORS = tuple(MAIN_VALIDATOR_NODE_MAP.keys())


# ---------------------------------------------------------------------------
# Fan-out helpers
# ---------------------------------------------------------------------------

def _get_validators_to_run(state: dict) -> tuple:
    retry_count = state.get("main_retry_count", 0)
    failed_validators = [
        v for v in state.get("main_failed_validators", [])
        if v in MAIN_VALIDATOR_NODE_MAP
    ]
    should_full_recheck = (
        retry_count == 0
        or not failed_validators
        or (MAIN_FULL_RECHECK_INTERVAL > 0 and retry_count % MAIN_FULL_RECHECK_INTERVAL == 0)
    )
    return MAIN_VALIDATORS if should_full_recheck else tuple(failed_validators)


def fan_out_main_checks(state: dict):
    """主干问题生成后，失败项优先复检；按周期触发全量复检。"""
    validators_to_run = _get_validators_to_run(state)
    patched_state = {**state, "main_checks_expected": len(validators_to_run)}
    return [Send(MAIN_VALIDATOR_NODE_MAP[v], patched_state) for v in validators_to_run]




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
    result = variant_alignment_node(state)
    if result.get("validation_results", [{}])[0].get("passed", True):
        result["sub_pipelines_done"] = 1
    return result


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
    result = scaffold_alignment_node(state)
    if result.get("validation_results", [{}])[0].get("passed", True):
        result["sub_pipelines_done"] = 1
    return result


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
    """每个主干检验 Agent 完成后触发一次，通过计数器判断是否全部到齐。
    未到齐时返回空 dict（no-op），到齐后才汇总结果。"""
    done = state.get("main_checks_done", 0)
    expected = state.get("main_checks_expected", len(MAIN_VALIDATORS))

    if done < expected:
        return {}

    results = state.get("validation_results", [])
    checked_results = [
        vr for vr in results
        if vr.get("validator") in MAIN_VALIDATORS
    ]
    failed_validators = [
        vr.get("validator")
        for vr in checked_results
        if not vr.get("passed", True)
    ]
    passed_all = all(
        vr.get("passed", True) for vr in checked_results
    )
    status = "全部通过" if passed_all else "存在未通过项"
    mode = "全量复检" if len(checked_results) >= len(MAIN_VALIDATORS) else "失败项优先复检"
    return {
        "main_checks_done": -999,
        "main_failed_validators": failed_validators,
        "progress_messages": ["[系统] 主干问题检验完成（%s，%s）" % (mode, status)],
    }


def route_after_main_checks(state: dict) -> str:
    done = state.get("main_checks_done", 0)
    expected = state.get("main_checks_expected", len(MAIN_VALIDATORS))

    if done > 0 and done < expected:
        return "wait_more"

    for vr in state.get("validation_results", []):
        if vr.get("validator") in MAIN_VALIDATORS:
            if not vr.get("passed", True):
                if state.get("main_retry_count", 0) < MAX_VALIDATION_RETRIES:
                    return "retry_main"
    return "continue"


def bump_main_retry(state: dict) -> dict:
    new_count = state.get("main_retry_count", 0) + 1

    # 保留本轮三个验证器的结果，供主干生成器下一轮读取
    saved_feedback = [
        vr for vr in state.get("validation_results", [])
        if vr.get("validator") in MAIN_VALIDATORS
    ]
    failed_validators = [
        vr.get("validator")
        for vr in saved_feedback
        if not vr.get("passed", True)
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
        "main_failed_validators": failed_validators,
        "progress_messages": ["[系统] 主干问题检验未通过，第 %d 次重新生成%s" % (new_count, feedback_info)],
    }




# ---------------------------------------------------------------------------
# Wait for both variant+scaffold to finish before map_integration
# ---------------------------------------------------------------------------

REQUIRED_SUB_PIPELINES = 2

def aggregate_sub_pipelines(state: dict) -> dict:
    """每条通过的流水线到达此节点时触发一次，累加计数。
    当两条都到达后，下游路由函数才放行到 map_integration。"""
    done = state.get("sub_pipelines_done", 0)
    if done >= REQUIRED_SUB_PIPELINES:
        vr_retry = state.get("variant_retry_count", 0)
        sc_retry = state.get("scaffold_retry_count", 0)
        v_note = "（经 %d 次重试）" % vr_retry if vr_retry > 0 else ""
        s_note = "（经 %d 次重试）" % sc_retry if sc_retry > 0 else ""
        return {
            "sub_pipelines_done": -999,
            "progress_messages": [
                "[系统] 变式问题%s与支架问题%s均已通过检验，开始整合教学地图..." % (v_note, s_note)
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
        {"retry_main": "bump_main_retry", "continue": "fan_out_gen", "wait_more": END},
    )
    workflow.add_node("fan_out_gen", lambda state: {"progress_messages": ["[系统] 主干检验通过，并行生成变式与支架问题..."]})
    # fan_out_gen 用普通双出边连接两个生成节点，LangGraph 并行执行
    workflow.add_edge("fan_out_gen", "variant_question")
    workflow.add_edge("fan_out_gen", "scaffold_question")
    workflow.add_edge("bump_main_retry", "main_question_chain")

    # === Phase 3: 变式/支架独立流水线（各自生成 → 检验 → 重试/通过 → fan-in）===
    workflow.add_edge("variant_question", "variant_check")
    workflow.add_conditional_edges(
        "variant_check",
        route_after_variant_check,
        {"retry_variant": "bump_variant_retry", "done_variant": "aggregate_sub_pipelines"},
    )
    workflow.add_edge("bump_variant_retry", "variant_question")

    workflow.add_edge("scaffold_question", "scaffold_check")
    workflow.add_conditional_edges(
        "scaffold_check",
        route_after_scaffold_check,
        {"retry_scaffold": "bump_scaffold_retry", "done_scaffold": "aggregate_sub_pipelines"},
    )
    workflow.add_edge("bump_scaffold_retry", "scaffold_question")

    # === Phase 4: 计数器门控 fan-in → 地图整合 ===
    # aggregate_sub_pipelines 每条通过的流水线触发一次，计数器累加；
    # 只有两条都到达（counter >= 2）才路由到 map_integration，否则结束该分支
    workflow.add_conditional_edges(
        "aggregate_sub_pipelines",
        route_after_sub_aggregate,
        {"do_integration": "map_integration", "wait_more": END},
    )
    workflow.add_edge("map_integration", END)

    return workflow.compile()
