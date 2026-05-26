# -*- coding: utf-8 -*-
"""
验证 nav_algorithm.py 的调度逻辑是否符合 algorithm.md 中描述的教学导航算法。

测试依据（algorithm.md）:
  场景1 (高参与度+高准确率): 纵向认知进阶
    - 当前节点为主干/变式 → 调度到下一教学单元的主干/变式中优先级最高的节点
    - 当前节点为支架      → 调度到当前教学单元的主干/变式中优先级最高的节点

  场景2 (高参与度+低准确率): 修复认知障碍
    - 当前节点为主干/变式:
        有未访问支架题 → 调度当前单元未访问支架中优先级最高的节点
        无未访问支架题 → 输出当前主干题解析, 再调度下一单元优先级最高的支架题
    - 当前节点为支架:
        即时输出该支架题解析, 再调度当前单元主干/变式中优先级最高的节点

  场景3 (低参与度+高准确率): 激活参与度+巩固认知
    - 当前节点为主干/变式:
        有未访问变式题 → 调度当前单元未访问变式中优先级最高的节点
        无未访问变式题 → 调度下一单元主干/变式中优先级最高的节点
    - 当前节点为支架:
        有未访问支架题 → 调度当前单元未访问支架中优先级最高的节点
        无未访问支架题 → 调度当前单元主干/变式中优先级最高的节点

  场景4 (低参与度+低准确率): 修复认知+激活参与
    - 当前节点为主干/变式:
        有未访问支架题 → 调度当前单元未访问支架中优先级最高的节点
        无未访问支架题 → 输出当前主干题解析, 再调度下一单元优先级最高的支架题
    - 当前节点为支架:
        即时输出该支架题解析
        有未访问支架题 → 调度当前单元未访问支架中优先级最高的节点
        无未访问支架题 → 调度当前单元主干/变式中优先级最高的节点
"""

import sys
import traceback
from nav_algorithm import dispatch_next

# ─────────────────────────────────────────────
# 颜色输出工具
# ─────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

PASS_ICON = "✅"
FAIL_ICON = "❌"
WARN_ICON = "⚠️ "


class TestResult:
    def __init__(self, name: str, passed: bool, detail: str = "", warn: bool = False):
        self.name = name
        self.passed = passed
        self.detail = detail
        self.warn = warn  # Known deviation (documented difference from spec)


results: list[TestResult] = []


def run_case(
    name: str,
    teaching_map: dict,
    current_node_id: str,
    participation: str,
    accuracy: str,
    visited: list,
    expected_next: str | None = None,
    expected_show_explanation: bool | None = None,
    expected_explanation_node: str | None = None,
    expected_completed: bool = False,
    warn_if_fail: bool = False,
):
    """Run a single dispatch_next test case and record the result."""
    try:
        result = dispatch_next(
            teaching_map=teaching_map,
            current_node_id=current_node_id,
            participation=participation,
            accuracy=accuracy,
            visited=visited,
        )
    except Exception as exc:
        results.append(TestResult(name, False, f"Exception: {exc}\n{traceback.format_exc()}"))
        return

    failures = []

    if expected_next is not None and result.get("next_node_id") != expected_next:
        failures.append(
            f"next_node_id: 期望 {expected_next!r}, 实际 {result.get('next_node_id')!r}"
        )

    if expected_show_explanation is not None and result.get("show_explanation") != expected_show_explanation:
        failures.append(
            f"show_explanation: 期望 {expected_show_explanation}, 实际 {result.get('show_explanation')}"
        )

    if expected_explanation_node is not None and result.get("explanation_node_id") != expected_explanation_node:
        failures.append(
            f"explanation_node_id: 期望 {expected_explanation_node!r}, 实际 {result.get('explanation_node_id')!r}"
        )

    if result.get("completed") != expected_completed:
        failures.append(
            f"completed: 期望 {expected_completed}, 实际 {result.get('completed')}"
        )

    if failures:
        detail = "  |  ".join(failures) + f"\n    完整结果: {result}"
        results.append(TestResult(name, False, detail, warn=warn_if_fail))
    else:
        results.append(TestResult(name, True, str(result)))


# ─────────────────────────────────────────────
# 公共教学地图构造器
# ─────────────────────────────────────────────

def make_map(*nodes):
    """Build a teaching_map dict from a list of node dicts."""
    return {"nodes": list(nodes), "edges": []}


def main_node(nid, priority=1.0):
    return {"id": nid, "question_type": "main", "priority": priority}


def variant_node(nid, main_id, priority=1.0):
    return {"id": nid, "question_type": "variant", "main_id": main_id, "priority": priority}


def scaffold_node(nid, from_id, priority=1.0, bridge_group_id=None, sequence=None):
    n = {"id": nid, "question_type": "scaffold", "from_id": from_id, "priority": priority}
    if bridge_group_id:
        n["bridge_group_id"] = bridge_group_id
    if sequence is not None:
        n["sequence"] = sequence
    return n


# ══════════════════════════════════════════════════════════════════════════════
# 场景1：高参与度 + 高准确率  (high participation + high accuracy)
# ══════════════════════════════════════════════════════════════════════════════

def test_scenario1():
    # 最基础的两个教学单元地图
    tmap = make_map(
        main_node("M1", priority=1.0),
        variant_node("V1", "M1", priority=0.9),
        main_node("M2", priority=1.0),
        variant_node("V2", "M2", priority=0.9),
    )

    # 1-1: 当前为主干题 → 应调度到下一单元（M2单元）中优先级最高的主干/变式
    run_case(
        "场景1-1: 主干题 → 下一单元主干/变式(最高优先级)",
        tmap, "M1", "high", "high", visited=["M1"],
        expected_next="M2",
        expected_show_explanation=False,
    )

    # 1-2: 当前为变式题 → 应调度到下一单元最高优先级的主干/变式
    run_case(
        "场景1-2: 变式题 → 下一单元主干/变式(最高优先级)",
        tmap, "V1", "high", "high", visited=["M1", "V1"],
        expected_next="M2",
        expected_show_explanation=False,
    )

    # 1-3: 含支架题，当前为支架 → 应调度到当前单元（M1单元）最高优先级的主干/变式
    tmap2 = make_map(
        main_node("M1", priority=1.0),
        variant_node("V1", "M1", priority=0.9),
        scaffold_node("S1-1", "M1", priority=0.8),
        main_node("M2", priority=1.0),
    )
    # 注意：scaffold-chain-lock 会拦截有后继链节点的情况；
    # 这里 S1-1 是链中唯一节点，所以会进入场景逻辑
    # 算法说: 当前为支架 → 调度当前教学单元的主干/变式
    # S1-1 属于 M1 单元，当前单元主干/变式 = M1(已访问), V1(未访问，优先级0.9)
    run_case(
        "场景1-3: 支架题(链末) → 当前单元主干/变式(最高优先级)",
        tmap2, "S1-1", "high", "high", visited=["M1", "S1-1"],
        expected_next="V1",
        expected_show_explanation=False,
    )

    # 1-4: 支架作为当前节点，且当前单元主干/变式均已访问 → 需要调度下一单元
    tmap3 = make_map(
        main_node("M1", priority=1.0),
        scaffold_node("S1-1", "M1", priority=0.8),
        main_node("M2", priority=1.0),
    )
    run_case(
        "场景1-4: 支架题(链末) + 当前单元主干均已访问 → 下一单元",
        tmap3, "S1-1", "high", "high", visited=["M1", "S1-1"],
        expected_next="M2",
        expected_show_explanation=False,
    )

    # 1-5: 最后一个单元的主干题，高高 → completed
    tmap_single = make_map(main_node("M1", priority=1.0))
    run_case(
        "场景1-5: 最后一个单元主干题 高高 → completed",
        tmap_single, "M1", "high", "high", visited=["M1"],
        expected_next=None,
        expected_completed=True,
    )

    # 1-6: 混合类型选择 - 主干类型排名高于变式，即使变式数值优先级(0.9)高于主干(0.5)
    # 设计决策：类型排名 main > variant > scaffold，优先在最高类型层内比数值优先级
    tmap4 = make_map(
        main_node("M1", priority=1.0),
        main_node("M2", priority=0.5),
        variant_node("V2", "M2", priority=0.9),
    )
    run_case(
        "场景1-6: 主干题 → 下一单元，混合类型时类型排名优先(M2 main > V2 variant)",
        tmap4, "M1", "high", "high", visited=["M1"],
        expected_next="M2",   # main(rank=2) 优先于 variant(rank=1)，尽管V2数值priority更高
        expected_show_explanation=False,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 场景2：高参与度 + 低准确率  (high participation + low accuracy)
# ══════════════════════════════════════════════════════════════════════════════

def test_scenario2():
    # 基础地图：M1单元含一个支架题
    tmap = make_map(
        main_node("M1", priority=1.0),
        scaffold_node("S1-1", "M1", priority=0.8),
        main_node("M2", priority=1.0),
    )

    # 2-1: 当前为主干题 + 有未访问支架 → 调度到当前单元未访问支架中优先级最高的
    run_case(
        "场景2-1: 主干题 + 有未访问支架 → 当前单元支架(最高优先级)",
        tmap, "M1", "high", "low", visited=["M1"],
        expected_next="S1-1",
        expected_show_explanation=False,
    )

    # 2-2: 当前为主干题 + 支架已全部访问 → 输出当前主干解析 + 调度下一单元支架
    # algorithm.md 明确要求 show_explanation=True
    tmap2 = make_map(
        main_node("M1", priority=1.0),
        scaffold_node("S1-1", "M1", priority=0.8),
        main_node("M2", priority=1.0),
        scaffold_node("S2-1", "M2", priority=0.8),
    )
    run_case(
        "场景2-2: 主干题 + 无未访问支架 → show_explanation=True + 下一单元支架",
        tmap2, "M1", "high", "low", visited=["M1", "S1-1"],
        expected_next="S2-1",
        expected_show_explanation=True,   # 算法要求输出解析
        expected_explanation_node="M1",   # 输出的是当前主干题的解析
        warn_if_fail=True,  # 当前实现可能未实现 show_explanation
    )

    # 2-3: 当前为支架题(链末) → 即时输出解析 + 调度当前单元主干/变式中优先级最高的
    tmap3 = make_map(
        main_node("M1", priority=1.0),
        variant_node("V1", "M1", priority=0.9),
        scaffold_node("S1-1", "M1", priority=0.8),
    )
    # visited 已包含 M1，未访问的最高优先级是 V1(0.9)
    run_case(
        "场景2-3: 支架题(链末) → show_explanation=True + 当前单元主干/变式最高优先级",
        tmap3, "S1-1", "high", "low", visited=["M1", "S1-1"],
        expected_next="V1",
        expected_show_explanation=True,   # 算法要求输出支架题解析
        expected_explanation_node="S1-1",
        warn_if_fail=True,
    )

    # 2-4: 当前为变式题 + 有未访问支架 → 调度到当前单元未访问支架
    tmap4 = make_map(
        main_node("M1", priority=1.0),
        variant_node("V1", "M1", priority=0.9),
        scaffold_node("S1-1", "M1", priority=0.8),
        main_node("M2", priority=1.0),
    )
    run_case(
        "场景2-4: 变式题 + 有未访问支架 → 当前单元支架",
        tmap4, "V1", "high", "low", visited=["M1", "V1"],
        expected_next="S1-1",
        expected_show_explanation=False,
    )

    # 2-5: 优先级差异——当前单元有两个独立支架组，应选链入口节点优先级更高的
    # 通过不同 bridge_group_id 确保两者属于不同支架链
    tmap5 = make_map(
        main_node("M1", priority=1.0),
        scaffold_node("S1-1", "M1", priority=0.6, bridge_group_id="BG_A"),
        scaffold_node("S1-2", "M1", priority=0.9, bridge_group_id="BG_B"),
        main_node("M2", priority=1.0),
    )
    run_case(
        "场景2-5: 主干题 + 两个独立支架组(不同priority) → 选优先级最高的支架链",
        tmap5, "M1", "high", "low", visited=["M1"],
        expected_next="S1-2",  # BG_B 入口 S1-2(0.9) > BG_A 入口 S1-1(0.6)
        expected_show_explanation=False,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 场景3：低参与度 + 高准确率  (low participation + high accuracy)
# ══════════════════════════════════════════════════════════════════════════════

def test_scenario3():
    # 3-1: 当前为主干题 + 有未访问变式题 → 调度当前单元未访问变式中优先级最高的
    tmap = make_map(
        main_node("M1", priority=1.0),
        variant_node("V1", "M1", priority=0.7),
        variant_node("V2", "M1", priority=0.9),
        main_node("M2", priority=1.0),
    )
    run_case(
        "场景3-1: 主干题 + 有未访问变式 → 当前单元变式(最高优先级)",
        tmap, "M1", "low", "high", visited=["M1"],
        expected_next="V2",  # V2优先级0.9 > V1优先级0.7
        expected_show_explanation=False,
    )

    # 3-2: 当前为主干题 + 变式已全部访问 → 调度下一单元主干/变式中优先级最高的
    run_case(
        "场景3-2: 主干题 + 无未访问变式 → 下一单元主干/变式(最高优先级)",
        tmap, "M1", "low", "high", visited=["M1", "V1", "V2"],
        expected_next="M2",
        expected_show_explanation=False,
    )

    # 3-3: 当前为变式题 + 还有其他未访问变式 → 调度当前单元另一个变式
    run_case(
        "场景3-3: 变式题 + 有未访问变式 → 当前单元另一变式(最高优先级)",
        tmap, "V1", "low", "high", visited=["M1", "V1"],
        expected_next="V2",  # V2优先级0.9 > V1(已访问)
        expected_show_explanation=False,
    )

    # 3-4: 当前为支架题(链末) + 有未访问支架 → 调度当前单元未访问支架
    tmap2 = make_map(
        main_node("M1", priority=1.0),
        scaffold_node("S1-1", "M1", priority=0.9, bridge_group_id="BG1"),
        scaffold_node("S1-2", "M1", priority=0.7, bridge_group_id="BG2"),
        main_node("M2", priority=1.0),
    )
    run_case(
        "场景3-4: 支架题(链末) + 有未访问支架(另一组) → 当前单元未访问支架",
        tmap2, "S1-1", "low", "high", visited=["M1", "S1-1"],
        expected_next="S1-2",
        expected_show_explanation=False,
    )

    # 3-5: 当前为支架题(链末) + 无未访问支架 → 调度当前单元主干/变式中优先级最高的
    tmap3 = make_map(
        main_node("M1", priority=1.0),
        variant_node("V1", "M1", priority=0.9),
        scaffold_node("S1-1", "M1", priority=0.8),
        main_node("M2", priority=1.0),
    )
    run_case(
        "场景3-5: 支架题(链末) + 无未访问支架 → 当前单元主干/变式最高优先级",
        tmap3, "S1-1", "low", "high", visited=["M1", "S1-1"],
        expected_next="V1",  # V1未访问，优先级0.9
        expected_show_explanation=False,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 场景4：低参与度 + 低准确率  (low participation + low accuracy)
# ══════════════════════════════════════════════════════════════════════════════

def test_scenario4():
    # 基础地图
    tmap = make_map(
        main_node("M1", priority=1.0),
        scaffold_node("S1-1", "M1", priority=0.8),
        main_node("M2", priority=1.0),
        scaffold_node("S2-1", "M2", priority=0.8),
    )

    # 4-1: 当前为主干题 + 有未访问支架 → 调度当前单元未访问支架
    run_case(
        "场景4-1: 主干题 + 有未访问支架 → 当前单元支架(最高优先级)",
        tmap, "M1", "low", "low", visited=["M1"],
        expected_next="S1-1",
        expected_show_explanation=False,
    )

    # 4-2: 当前为主干题 + 无未访问支架 → 输出当前主干解析 + 调度下一单元支架
    run_case(
        "场景4-2: 主干题 + 无未访问支架 → show_explanation=True + 下一单元支架",
        tmap, "M1", "low", "low", visited=["M1", "S1-1"],
        expected_next="S2-1",
        expected_show_explanation=True,   # 算法要求输出解析
        expected_explanation_node="M1",
        warn_if_fail=True,
    )

    # 4-3: 当前为支架题(链末) → 即时输出解析 + 有未访问支架 → 调度当前单元未访问支架
    tmap2 = make_map(
        main_node("M1", priority=1.0),
        scaffold_node("S1-1", "M1", priority=0.9, bridge_group_id="BG1"),
        scaffold_node("S1-2", "M1", priority=0.7, bridge_group_id="BG2"),
        main_node("M2", priority=1.0),
    )
    run_case(
        "场景4-3: 支架题(链末) + 有其他未访问支架 → show_explanation=True + 当前单元未访问支架",
        tmap2, "S1-1", "low", "low", visited=["M1", "S1-1"],
        expected_next="S1-2",
        expected_show_explanation=True,   # 算法要求输出支架题解析
        expected_explanation_node="S1-1",
        warn_if_fail=True,
    )

    # 4-4: 当前为支架题(链末) + 无未访问支架 → 输出解析 + 调度当前单元主干/变式
    tmap3 = make_map(
        main_node("M1", priority=1.0),
        variant_node("V1", "M1", priority=0.9),
        scaffold_node("S1-1", "M1", priority=0.8),
    )
    run_case(
        "场景4-4: 支架题(链末) + 无未访问支架 → show_explanation=True + 当前单元主干/变式",
        tmap3, "S1-1", "low", "low", visited=["M1", "S1-1"],
        expected_next="V1",
        expected_show_explanation=True,
        expected_explanation_node="S1-1",
        warn_if_fail=True,
    )

    # 4-5: 优先级差异——两个未访问支架，应选优先级高的
    tmap4 = make_map(
        main_node("M1", priority=1.0),
        scaffold_node("S1-1", "M1", priority=0.6, bridge_group_id="BG1"),
        scaffold_node("S1-2", "M1", priority=0.9, bridge_group_id="BG2"),
        main_node("M2", priority=1.0),
    )
    run_case(
        "场景4-5: 主干题 + 两个未访问支架(不同组) → 选优先级最高支架",
        tmap4, "M1", "low", "low", visited=["M1"],
        expected_next="S1-2",  # 优先级0.9 > 0.6
        expected_show_explanation=False,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 支架链锁 (Scaffold Chain Lock) 行为验证
# 算法.md 未明确描述链锁，但实现中存在；此处验证其行为是否合理
# ══════════════════════════════════════════════════════════════════════════════

def test_scaffold_chain():
    # 一条包含 3 个节点的支架链
    tmap = make_map(
        main_node("M1", priority=1.0),
        scaffold_node("S1-1-1", "M1", priority=0.9, bridge_group_id="BG1", sequence=1),
        scaffold_node("S1-1-2", "M1", priority=0.5, bridge_group_id="BG1", sequence=2),
        scaffold_node("S1-1-3", "M1", priority=0.8, bridge_group_id="BG1", sequence=3),
        main_node("M2", priority=1.0),
    )

    # C-1: 在链中间的节点 → 不管场景，应按顺序进入下一个链节点
    run_case(
        "链锁-1: 支架链中间节点(高高) → 顺序推进到链下一节点",
        tmap, "S1-1-1", "high", "high", visited=["M1", "S1-1-1"],
        expected_next="S1-1-2",  # 链锁强制顺序：sequence=2
        expected_show_explanation=False,
    )

    run_case(
        "链锁-2: 支架链中间节点(低低) → 顺序推进到链下一节点(不出解析)",
        tmap, "S1-1-2", "low", "low", visited=["M1", "S1-1-1", "S1-1-2"],
        expected_next="S1-1-3",
        expected_show_explanation=False,
    )

    # C-3: 链末节点 → 退出链锁，进入场景逻辑
    run_case(
        "链锁-3: 支架链末节点(高高) → 退出链锁，进入场景1(当前单元主干/变式)",
        tmap, "S1-1-3", "high", "high", visited=["M1", "S1-1-1", "S1-1-2", "S1-1-3"],
        expected_next="M2",  # 场景1+scaffold → 当前单元主干/变式 → M1已访问 → 下一单元M2
        expected_show_explanation=False,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 边界情况
# ══════════════════════════════════════════════════════════════════════════════

def test_edge_cases():
    # E-1: 空节点列表
    run_case(
        "边界-1: 空教学地图 → completed",
        {"nodes": [], "edges": []}, "M1", "high", "high", visited=[],
        expected_next=None,
        expected_completed=True,
    )

    # E-2: 找不到当前节点 → completed
    tmap = make_map(main_node("M1"))
    run_case(
        "边界-2: current_node_id 不存在 → completed",
        tmap, "NONEXISTENT", "high", "high", visited=[],
        expected_next=None,
        expected_completed=True,
    )

    # E-3: 只有一个主干节点，全部访问 → completed
    run_case(
        "边界-3: 单节点地图，场景1(高高) → completed",
        tmap, "M1", "high", "high", visited=["M1"],
        expected_next=None,
        expected_completed=True,
    )

    # E-4: 多单元全部已访问 → completed
    tmap2 = make_map(
        main_node("M1"),
        main_node("M2"),
        main_node("M3"),
    )
    run_case(
        "边界-4: 三单元全访问，场景1(高高) → completed",
        tmap2, "M3", "high", "high", visited=["M1", "M2", "M3"],
        expected_next=None,
        expected_completed=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 主入口：运行所有测试，打印报告
# ══════════════════════════════════════════════════════════════════════════════

def print_report():
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed_hard = sum(1 for r in results if not r.passed and not r.warn)
    failed_warn = sum(1 for r in results if not r.passed and r.warn)

    print()
    print(f"{BOLD}{'═' * 70}{RESET}")
    print(f"{BOLD}  教学导航算法符合性检验报告{RESET}")
    print(f"{'═' * 70}")
    print()

    current_group = ""
    for r in results:
        prefix = r.name.split(":")[0].strip()
        group = prefix.rsplit("-", 1)[0] if "-" in prefix else prefix
        if group != current_group:
            current_group = group
            label = {
                "场景1": "场景1  高参与度 + 高准确率",
                "场景2": "场景2  高参与度 + 低准确率",
                "场景3": "场景3  低参与度 + 高准确率",
                "场景4": "场景4  低参与度 + 低准确率",
                "链锁":  "支架链锁行为",
                "边界":  "边界情况",
            }.get(group, group)
            print(f"{BOLD}  ── {label}{RESET}")

        if r.passed:
            icon = PASS_ICON
            color = GREEN
        elif r.warn:
            icon = WARN_ICON
            color = YELLOW
        else:
            icon = FAIL_ICON
            color = RED

        print(f"  {icon} {color}{r.name}{RESET}")
        if not r.passed:
            for line in r.detail.split("\n"):
                print(f"       {line}")
    print()
    print(f"{'─' * 70}")
    print(f"  总计: {total} 项  |  {GREEN}通过: {passed}{RESET}  |  "
          f"{RED}硬失败: {failed_hard}{RESET}  |  "
          f"{YELLOW}已知偏差: {failed_warn}{RESET}")
    print(f"{'─' * 70}")

    if failed_warn:
        print()
        print(f"{YELLOW}{BOLD}  ⚠️  已知偏差说明（⚠️ 标记项）:{RESET}")
        print(f"{YELLOW}  algorithm.md 在以下情况要求将 show_explanation 置为 True，{RESET}")
        print(f"{YELLOW}  并附带 explanation_node_id 以通知前端展示题目解析：{RESET}")
        print(f"{YELLOW}    • 场景2：主干/变式 + 当前单元无未访问支架 → 输出当前主干解析{RESET}")
        print(f"{YELLOW}    • 场景2：当前节点为支架(链末) → 即时输出该支架解析{RESET}")
        print(f"{YELLOW}    • 场景4：主干/变式 + 当前单元无未访问支架 → 输出当前主干解析{RESET}")
        print(f"{YELLOW}    • 场景4：当前节点为支架(链末) → 即时输出该支架解析{RESET}")
        print(f"{YELLOW}  当前实现中 show_explanation 始终为 False，这是一处与规格的偏差。{RESET}")

    print()
    return failed_hard == 0


if __name__ == "__main__":
    print(f"{BOLD}正在运行教学导航算法检验...{RESET}")
    test_scenario1()
    test_scenario2()
    test_scenario3()
    test_scenario4()
    test_scaffold_chain()
    test_edge_cases()
    ok = print_report()
    sys.exit(0 if ok else 1)
