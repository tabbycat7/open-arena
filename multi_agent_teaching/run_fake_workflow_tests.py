"""Run workflow boundary tests with fake LLM API.

Usage:
  python multi_agent_teaching/run_fake_workflow_tests.py
  python multi_agent_teaching/run_fake_workflow_tests.py --scenarios all_pass main_retry_once
  python multi_agent_teaching/run_fake_workflow_tests.py --save-report multi_agent_teaching/fake_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class ScenarioResult:
    name: str
    ok: bool
    checks: List[str]
    errors: List[str]
    summary: Dict[str, Any]


def _build_initial_state() -> Dict[str, Any]:
    return {
        "subject": "math",
        "grade": "grade8",
        "teaching_goals": "Understand exponential function and compare values",
        "student_profile": "mixed class",
        "language_style": "concise",
        "attachment": "",
        "main_retry_count": 0,
        "variant_retry_count": 0,
        "scaffold_retry_count": 0,
        "sub_pipelines_done": 0,
        "main_validation_feedback": [],
        "variant_validation_feedback": [],
        "scaffold_validation_feedback": [],
        "progress_messages": [],
        "validation_results": [],
        "main_questions": [],
        "variant_questions": [],
        "scaffold_questions": [],
        "analysis_result": {},
        "map_construction_logic": {},
        "teaching_map": {"nodes": [], "edges": []},
    }


def _scenario_expectations() -> Dict[str, Dict[str, Any]]:
    return {
        "all_pass": {
            "main_retry_count": 0,
            "variant_retry_count": 0,
            "scaffold_retry_count": 0,
            "main_question_chain_calls": 1,
            "main_check_calls": 1,
            "variant_check_calls": 1,
            "scaffold_check_calls": 1,
            "min_main_questions": 4,
            "min_total_nodes": 8,
        },
        "main_retry_once": {
            "main_retry_count": 1,
            "main_question_chain_calls": 2,
            "main_check_calls": 2,
            "min_total_nodes": 8,
        },
        "main_retry_twice": {
            "main_retry_count": 2,
            "main_question_chain_calls": 3,
            "main_check_calls": 3,
            "min_total_nodes": 8,
        },
        "variant_retry_exhaust": {
            "variant_retry_count": 3,
            "variant_question_calls": 4,
            "variant_check_calls": 4,
            "min_total_nodes": 8,
        },
        "scaffold_retry_exhaust": {
            "scaffold_retry_count": 3,
            "scaffold_question_calls": 4,
            "scaffold_check_calls": 4,
            "min_total_nodes": 8,
        },
        "validator_parse_error": {
            "main_retry_count": 0,
            "variant_retry_count": 0,
            "scaffold_retry_count": 0,
            "min_total_nodes": 8,
            "note": "Current validators fallback to passed=true on parse errors",
        },
        "generator_parse_error_main": {
            "main_retry_count": 0,
            "expected_main_questions": 0,
            "min_total_nodes": 4,
        },
    }


def _counter(counters: Dict[str, int], scenario: str, agent: str) -> int:
    return counters.get(f"{scenario}:{agent}", 0)


def _assert_equal(errors: List[str], checks: List[str], title: str, got: Any, expected: Any) -> None:
    if got == expected:
        checks.append(f"PASS: {title} == {expected}")
    else:
        errors.append(f"FAIL: {title}, expected={expected}, got={got}")


def _assert_at_least(errors: List[str], checks: List[str], title: str, got: int, minimum: int) -> None:
    if got >= minimum:
        checks.append(f"PASS: {title} >= {minimum}")
    else:
        errors.append(f"FAIL: {title}, expected >= {minimum}, got={got}")


def _run_one_scenario(name: str) -> ScenarioResult:
    os.environ["TEACHING_MAP_FAKE_API"] = "1"
    os.environ["TEACHING_MAP_FAKE_SCENARIO"] = name

    from agents.fake_api import get_call_counters, reset_runtime_state
    from agents.graph import build_graph

    reset_runtime_state()

    checks: List[str] = []
    errors: List[str] = []

    graph = build_graph()
    final_state = graph.invoke(_build_initial_state(), config={"recursion_limit": 200})

    counters = get_call_counters()
    expectations = _scenario_expectations().get(name, {})

    _assert_equal(errors, checks, "main_retry_count", final_state.get("main_retry_count", 0), expectations.get("main_retry_count", final_state.get("main_retry_count", 0)))

    if "variant_retry_count" in expectations:
        _assert_equal(errors, checks, "variant_retry_count", final_state.get("variant_retry_count", 0), expectations["variant_retry_count"])
    if "scaffold_retry_count" in expectations:
        _assert_equal(errors, checks, "scaffold_retry_count", final_state.get("scaffold_retry_count", 0), expectations["scaffold_retry_count"])

    if "main_question_chain_calls" in expectations:
        _assert_equal(errors, checks, "main_question_chain_calls", _counter(counters, name, "main_question_chain"), expectations["main_question_chain_calls"])
    if "variant_question_calls" in expectations:
        _assert_equal(errors, checks, "variant_question_calls", _counter(counters, name, "variant_question"), expectations["variant_question_calls"])
    if "scaffold_question_calls" in expectations:
        _assert_equal(errors, checks, "scaffold_question_calls", _counter(counters, name, "scaffold_question"), expectations["scaffold_question_calls"])
    if "variant_check_calls" in expectations:
        _assert_equal(errors, checks, "variant_check_calls", _counter(counters, name, "variant_alignment"), expectations["variant_check_calls"])
    if "scaffold_check_calls" in expectations:
        _assert_equal(errors, checks, "scaffold_check_calls", _counter(counters, name, "scaffold_alignment"), expectations["scaffold_check_calls"])
    if "main_check_calls" in expectations:
        _assert_equal(errors, checks, "main_check_calls", _counter(counters, name, "integrated_main_question_validator"), expectations["main_check_calls"])

    main_questions = final_state.get("main_questions", [])
    total_nodes = len(final_state.get("teaching_map", {}).get("nodes", []))

    if "min_main_questions" in expectations:
        _assert_at_least(errors, checks, "main_questions_count", len(main_questions), expectations["min_main_questions"])
    if "expected_main_questions" in expectations:
        _assert_equal(errors, checks, "main_questions_count", len(main_questions), expectations["expected_main_questions"])
    if "min_total_nodes" in expectations:
        _assert_at_least(errors, checks, "teaching_map_nodes", total_nodes, expectations["min_total_nodes"])

    summary = {
        "main_retry_count": final_state.get("main_retry_count", 0),
        "variant_retry_count": final_state.get("variant_retry_count", 0),
        "scaffold_retry_count": final_state.get("scaffold_retry_count", 0),
        "main_questions": len(main_questions),
        "variant_questions": len(final_state.get("variant_questions", [])),
        "scaffold_questions": len(final_state.get("scaffold_questions", [])),
        "map_nodes": total_nodes,
        "map_edges": len(final_state.get("teaching_map", {}).get("edges", [])),
        "call_counters": counters,
        "notes": expectations.get("note", ""),
    }

    return ScenarioResult(
        name=name,
        ok=not errors,
        checks=checks,
        errors=errors,
        summary=summary,
    )


def _print_result(result: ScenarioResult) -> None:
    status = "OK" if result.ok else "FAIL"
    print(f"\n=== [{status}] {result.name} ===")
    for line in result.checks:
        print(line)
    for line in result.errors:
        print(line)
    print("Summary:")
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fake API workflow boundary tests")
    parser.add_argument(
        "--scenarios",
        nargs="*",
        default=[
            "all_pass",
            "main_retry_once",
            "main_retry_twice",
            "variant_retry_exhaust",
            "scaffold_retry_exhaust",
            "validator_parse_error",
            "generator_parse_error_main",
        ],
        help="Scenario names to run",
    )
    parser.add_argument("--save-report", default="", help="Save report to JSON file")
    args = parser.parse_args()

    results: List[ScenarioResult] = []
    for scenario in args.scenarios:
        try:
            results.append(_run_one_scenario(scenario))
        except Exception as exc:
            results.append(
                ScenarioResult(
                    name=scenario,
                    ok=False,
                    checks=[],
                    errors=[f"Unhandled exception: {exc}", traceback.format_exc()],
                    summary={},
                )
            )

    for item in results:
        _print_result(item)

    passed = sum(1 for r in results if r.ok)
    total = len(results)
    print(f"\nFinal: {passed}/{total} scenarios passed")

    if args.save_report:
        report_path = Path(args.save_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = [
            {
                "name": r.name,
                "ok": r.ok,
                "checks": r.checks,
                "errors": r.errors,
                "summary": r.summary,
            }
            for r in results
        ]
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report written to: {report_path}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
