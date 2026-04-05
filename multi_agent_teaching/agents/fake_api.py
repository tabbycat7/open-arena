"""Deterministic fake LLM API for workflow boundary testing.

Enable by setting:
- TEACHING_MAP_FAKE_API=1
- TEACHING_MAP_FAKE_SCENARIO=<scenario_name>

Optional:
- TEACHING_MAP_FAKE_SCENARIO_FILE=<json file path>
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class FakeResponse:
    content: str


_RUNTIME_LOCK = threading.Lock()
_RUNTIME_STATE: Dict[str, Any] = {
    "calls": {},
}


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def _analysis_result() -> Dict[str, Any]:
    return {
        "subject_grade": {"subject": "Math", "grade": "Grade 8", "inferred_topic": "Exponential Function"},
        "teaching_goals_breakdown": [
            {
                "goal_id": "G1",
                "goal_text": "Understand core rules of exponential function",
                "sub_goals": [
                    {
                        "sub_goal_id": "G1-1",
                        "description": "Identify exponential function definition",
                        "bloom_level": "理解",
                        "knowledge_points_covered": ["KP1"],
                    },
                    {
                        "sub_goal_id": "G1-2",
                        "description": "Use monotonicity for comparison",
                        "bloom_level": "应用",
                        "knowledge_points_covered": ["KP3", "KP4"],
                    },
                ],
            }
        ],
        "knowledge_graph": {
            "nodes": [
                {"kp_id": "KP1", "name": "Definition", "is_key_point": True, "is_difficult_point": False},
                {"kp_id": "KP2", "name": "Graph shape", "is_key_point": True, "is_difficult_point": False},
                {"kp_id": "KP3", "name": "Monotonicity", "is_key_point": True, "is_difficult_point": True},
                {"kp_id": "KP4", "name": "Comparison", "is_key_point": True, "is_difficult_point": True},
            ],
            "edges": [
                {"from": "KP1", "to": "KP2", "relation_type": "前置", "cognitive_gap": "中"},
                {"from": "KP2", "to": "KP3", "relation_type": "前置", "cognitive_gap": "大"},
                {"from": "KP3", "to": "KP4", "relation_type": "前置", "cognitive_gap": "中"},
            ],
        },
        "student_profile_analysis": {
            "overall_cognitive_level": "mixed",
            "prior_knowledge_summary": ["power rules", "basic plotting"],
            "advanced": {"cognitive_strengths": ["pattern discovery"]},
            "struggling": {
                "cognitive_barriers": ["abstract transfer"],
                "support_needs": ["small-step bridge questions"],
            },
        },
        "teaching_focus": {
            "difficult_points": ["KP3", "KP4"],
            "error_prone_points": ["a>0 and a!=1"],
        },
        "goal_situation_alignment": {
            "recommended_teaching_sequence": ["KP1", "KP2", "KP3", "KP4"],
            "cognitive_gap_assessment": "moderate",
            "differentiation_targets": {
                "advanced": ["analyze and justify"],
                "normal": ["apply and explain"],
                "struggling": ["remember and apply"],
            },
        },
    }


def _map_logic() -> Dict[str, Any]:
    return {
        "main_question_chain": [
            {
                "id": "M1",
                "sequence": 1,
                "teaching_function": "认知锚定",
                "knowledge_points": ["KP1"],
                "sub_goals": ["G1-1"],
                "difficulty": 0.6,
            },
            {
                "id": "M2",
                "sequence": 2,
                "teaching_function": "核心建构",
                "knowledge_points": ["KP2"],
                "sub_goals": ["G1-1"],
                "difficulty": 0.72,
            },
            {
                "id": "M3",
                "sequence": 3,
                "teaching_function": "认知冲突/深化",
                "knowledge_points": ["KP3"],
                "sub_goals": ["G1-2"],
                "difficulty": 0.82,
            },
            {
                "id": "M4",
                "sequence": 4,
                "teaching_function": "迁移整合",
                "knowledge_points": ["KP3", "KP4"],
                "sub_goals": ["G1-2"],
                "difficulty": 0.92,
            },
        ],
        "variant_question_plans": [
            {"id": "V1-1", "main_id": "M1"},
            {"id": "V2-1", "main_id": "M2"},
            {"id": "V3-1", "main_id": "M3"},
            {"id": "V4-1", "main_id": "M4"},
        ],
        "scaffold_question_plans": [
            {"id": "S1-1", "from_id": "M1", "to_id": "M2"},
            {"id": "S2-1", "from_id": "M2", "to_id": "M3"},
            {"id": "S3-1", "from_id": "M3", "to_id": "M4"},
        ],
    }


def _main_questions(version: int = 1) -> List[Dict[str, Any]]:
    suffix = "" if version == 1 else f" (rev{version})"
    return [
        {
            "id": "M1",
            "content": f"What pattern do you notice when a value doubles every hour{suffix}?",
            "knowledge_points": ["KP1"],
            "bloom_level": "应用",
            "difficulty": 0.6,
            "teaching_function": "认知锚定",
            "design_intent": "activate prior knowledge",
        },
        {
            "id": "M2",
            "content": f"After plotting y=2^x, what feature stands out first{suffix}?",
            "knowledge_points": ["KP2"],
            "bloom_level": "分析",
            "difficulty": 0.72,
            "teaching_function": "核心建构",
            "design_intent": "construct graph understanding",
        },
        {
            "id": "M3",
            "content": f"Why must a>1 and 0<a<1 lead to opposite trend directions{suffix}?",
            "knowledge_points": ["KP3"],
            "bloom_level": "评价",
            "difficulty": 0.82,
            "teaching_function": "认知冲突/深化",
            "design_intent": "force justification",
        },
        {
            "id": "M4",
            "content": f"Can one rule compare 3^1.2 and 0.3^-0.5 without calculator{suffix}?",
            "knowledge_points": ["KP3", "KP4"],
            "bloom_level": "创造",
            "difficulty": 0.92,
            "teaching_function": "迁移整合",
            "design_intent": "transfer to mixed context",
        },
    ]


def _variant_questions(version: int = 1) -> List[Dict[str, Any]]:
    suffix = "" if version == 1 else f" rev{version}"
    return [
        {
            "id": "V1-1",
            "content": f"A rumor spreads by triple each day{suffix}; what does that suggest about growth shape?",
            "main_id": "M1",
            "knowledge_points": ["KP1"],
            "bloom_level": "应用",
            "difficulty": 0.55,
            "strategy": "生活迁移",
            "design_intent": "same core with new context",
        },
        {
            "id": "V2-1",
            "content": f"Is y=(1/3)^x steeper than y=3^x near x=0{suffix}?",
            "main_id": "M2",
            "knowledge_points": ["KP2", "KP3"],
            "bloom_level": "分析",
            "difficulty": 0.65,
            "strategy": "对比冲突",
            "design_intent": "force distinction",
        },
        {
            "id": "V3-1",
            "content": f"Someone claims y=1^x is exponential{suffix}; agree or reject?",
            "main_id": "M3",
            "knowledge_points": ["KP3"],
            "bloom_level": "评价",
            "difficulty": 0.7,
            "strategy": "反例追问",
            "design_intent": "boundary check",
        },
        {
            "id": "V4-1",
            "content": f"Two bacteria grow with different bases{suffix}; when can the slower start overtake?",
            "main_id": "M4",
            "knowledge_points": ["KP4"],
            "bloom_level": "应用",
            "difficulty": 0.75,
            "strategy": "情景替换",
            "design_intent": "apply comparison",
        },
    ]


def _scaffold_questions(version: int = 1) -> List[Dict[str, Any]]:
    suffix = "" if version == 1 else f" rev{version}"
    return [
        {
            "id": "S1-1",
            "content": f"For y=2^x, what is y when x=0{suffix}?",
            "from_id": "M1",
            "to_id": "M2",
            "knowledge_points": ["KP1"],
            "bloom_level": "记忆",
            "difficulty": 0.3,
            "bridge_function": "activate base point",
            "design_intent": "low-stress warm-up",
        },
        {
            "id": "S2-1",
            "content": f"If x increases by 1, how does y=2^x change{suffix}?",
            "from_id": "M2",
            "to_id": "M3",
            "knowledge_points": ["KP2"],
            "bloom_level": "理解",
            "difficulty": 0.35,
            "bridge_function": "bridge shape to trend",
            "design_intent": "prepare monotonicity",
        },
        {
            "id": "S3-1",
            "content": f"Which is bigger, 2^3 or 2^2{suffix}? Why?",
            "from_id": "M3",
            "to_id": "M4",
            "knowledge_points": ["KP3"],
            "bloom_level": "理解",
            "difficulty": 0.4,
            "bridge_function": "bridge trend to comparison",
            "design_intent": "easy transition",
        },
    ]


def _validator_pass(name: str, total: int) -> Dict[str, Any]:
    return {
        "validator": name,
        "passed": True,
        "total_score": total,
        "feedback": {"must_fix": [], "should_fix": []},
        "issues": [],
        "overall_assessment": "ok",
    }


def _main_fail(name: str, total: int, item_id: str = "M2") -> Dict[str, Any]:
    return {
        "validator": name,
        "passed": False,
        "total_score": total,
        "feedback": {
            "must_fix": [
                {
                    "id": item_id,
                    "action": "rewrite this node",
                    "rewrite_direction": "make it single-focus and class-friendly",
                }
            ],
            "should_fix": [],
        },
        "issues": [
            {
                "id": item_id,
                "severity": "major",
                "issue_type": "quality",
                "description": "insufficient quality",
                "suggestion": "rewrite",
            }
        ],
        "overall_assessment": "need retry",
        "structure_adjustment": {
            "allow_increase_main_questions": False,
            "suggested_main_question_count": 4,
            "insertion_after_node": None,
            "new_node_function": "",
            "reason": "",
        },
    }


def _variant_fail() -> Dict[str, Any]:
    return {
        "validator": "variant_alignment",
        "passed": False,
        "total_score": 2,
        "feedback": {
            "must_fix": [
                {
                    "id": "V2-1",
                    "action": "reduce pseudo-variant risk",
                    "rewrite_direction": "change context but keep core",
                }
            ],
            "should_fix": [],
        },
        "issues": [
            {
                "id": "V2-1",
                "severity": "major",
                "issue_type": "pseudo_variant",
                "description": "too similar to main",
                "suggestion": "add contrast context",
            }
        ],
        "overall_assessment": "fail",
    }


def _scaffold_fail() -> Dict[str, Any]:
    return {
        "validator": "scaffold_alignment",
        "passed": False,
        "total_score": 3,
        "feedback": {
            "must_fix": [
                {
                    "id": "S2-1",
                    "action": "simplify phrasing",
                    "rewrite_direction": "make it easier for struggling learners",
                }
            ],
            "should_fix": [],
        },
        "issues": [
            {
                "id": "S2-1",
                "severity": "major",
                "issue_type": "not_scaffolded_enough",
                "description": "difficulty too high",
                "suggestion": "break down question",
            }
        ],
        "overall_assessment": "fail",
    }


def _builtin_scenarios() -> Dict[str, Dict[str, List[Any]]]:
    pass_main_check = _validator_pass("integrated_main_question_validator", 8)
    pass_variant = _validator_pass("variant_alignment", 10)
    pass_scaffold = _validator_pass("scaffold_alignment", 10)

    return {
        "all_pass": {
            "learning_analysis": [_analysis_result()],
            "teaching_logic_design": [_map_logic()],
            "main_question_chain": [_main_questions(1)],
            "variant_question": [_variant_questions(1)],
            "scaffold_question": [_scaffold_questions(1)],
            "integrated_main_question_validator": [pass_main_check],
            "variant_alignment": [pass_variant],
            "scaffold_alignment": [pass_scaffold],
        },
        "main_retry_once": {
            "learning_analysis": [_analysis_result()],
            "teaching_logic_design": [_map_logic()],
            "main_question_chain": [_main_questions(1), _main_questions(2)],
            "variant_question": [_variant_questions(1)],
            "scaffold_question": [_scaffold_questions(1)],
            "integrated_main_question_validator": [_main_fail("integrated_main_question_validator", 4), pass_main_check],
            "variant_alignment": [pass_variant],
            "scaffold_alignment": [pass_scaffold],
        },
        "main_retry_twice": {
            "learning_analysis": [_analysis_result()],
            "teaching_logic_design": [_map_logic()],
            "main_question_chain": [_main_questions(1), _main_questions(2), _main_questions(3)],
            "variant_question": [_variant_questions(1)],
            "scaffold_question": [_scaffold_questions(1)],
            "integrated_main_question_validator": [_main_fail("integrated_main_question_validator", 4), _main_fail("integrated_main_question_validator", 5), pass_main_check],
            "variant_alignment": [pass_variant],
            "scaffold_alignment": [pass_scaffold],
        },
        "variant_retry_exhaust": {
            "learning_analysis": [_analysis_result()],
            "teaching_logic_design": [_map_logic()],
            "main_question_chain": [_main_questions(1)],
            "variant_question": [_variant_questions(1), _variant_questions(2), _variant_questions(3), _variant_questions(4)],
            "scaffold_question": [_scaffold_questions(1)],
            "integrated_main_question_validator": [pass_main_check],
            "variant_alignment": [_variant_fail(), _variant_fail(), _variant_fail(), _variant_fail()],
            "scaffold_alignment": [pass_scaffold],
        },
        "scaffold_retry_exhaust": {
            "learning_analysis": [_analysis_result()],
            "teaching_logic_design": [_map_logic()],
            "main_question_chain": [_main_questions(1)],
            "variant_question": [_variant_questions(1)],
            "scaffold_question": [_scaffold_questions(1), _scaffold_questions(2), _scaffold_questions(3), _scaffold_questions(4)],
            "integrated_main_question_validator": [pass_main_check],
            "variant_alignment": [pass_variant],
            "scaffold_alignment": [_scaffold_fail(), _scaffold_fail(), _scaffold_fail(), _scaffold_fail()],
        },
        "validator_parse_error": {
            "learning_analysis": [_analysis_result()],
            "teaching_logic_design": [_map_logic()],
            "main_question_chain": [_main_questions(1)],
            "variant_question": [_variant_questions(1)],
            "scaffold_question": [_scaffold_questions(1)],
            "integrated_main_question_validator": ["NOT_JSON"],
            "variant_alignment": ["NOT_JSON"],
            "scaffold_alignment": ["NOT_JSON"],
        },
        "generator_parse_error_main": {
            "learning_analysis": [_analysis_result()],
            "teaching_logic_design": [_map_logic()],
            "main_question_chain": ["NOT_JSON"],
            "variant_question": [_variant_questions(1)],
            "scaffold_question": [_scaffold_questions(1)],
            "integrated_main_question_validator": [pass_main_check],
            "variant_alignment": [pass_variant],
            "scaffold_alignment": [pass_scaffold],
        },
    }


BUILTIN_SCENARIOS = _builtin_scenarios()


def _load_external_scenarios() -> Dict[str, Any]:
    file_path = os.getenv("TEACHING_MAP_FAKE_SCENARIO_FILE", "").strip()
    if not file_path:
        return {}

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"TEACHING_MAP_FAKE_SCENARIO_FILE not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "scenarios" in data and isinstance(data["scenarios"], dict):
        return data["scenarios"]

    if isinstance(data, dict):
        return data

    raise ValueError("Invalid fake scenario file format")


def _resolve_scenario_data() -> Dict[str, Dict[str, List[Any]]]:
    merged = dict(BUILTIN_SCENARIOS)
    merged.update(_load_external_scenarios())
    return merged


def _detect_agent(prompt: str) -> str:
    text = prompt or ""
    if "任务一：教学目标解析" in text and "任务二：知识点图谱构建" in text:
        return "learning_analysis"
    if (
        ("教学地图架构师" in text or "教学逻辑架构师" in text)
        and "主干问题链规划" in text
    ):
        return "teaching_logic_design"
    if "主干问题规划蓝图" in text and "主干问题链" not in text:
        return "main_question_chain"
    if "变式问题规划蓝图" in text:
        return "variant_question"
    if "支架问题规划蓝图" in text:
        return "scaffold_question"
    if "教学设计与课堂问题质量评估专家" in text or "教学蓝图 + 主干问题链" in text:
        return "integrated_main_question_validator"
    if "变式教学设计评估专家" in text:
        return "variant_alignment"
    if "支架式教学设计评估专家" in text:
        return "scaffold_alignment"
    raise ValueError("Fake API cannot detect agent from prompt. Add a stronger keyword rule.")


def _response_to_content(raw: Any) -> str:
    if isinstance(raw, (dict, list)):
        return _json(raw)
    return str(raw)


def _pick_response(scenario_name: str, agent: str) -> str:
    scenarios = _resolve_scenario_data()
    if scenario_name not in scenarios:
        names = ", ".join(sorted(scenarios.keys()))
        raise KeyError(f"Unknown fake scenario '{scenario_name}'. Available: {names}")

    scenario = scenarios[scenario_name]
    if agent not in scenario:
        raise KeyError(f"Scenario '{scenario_name}' has no response script for agent '{agent}'")

    key = f"{scenario_name}:{agent}"
    with _RUNTIME_LOCK:
        nth = _RUNTIME_STATE["calls"].get(key, 0)
        _RUNTIME_STATE["calls"][key] = nth + 1

    sequence = scenario[agent]
    if not isinstance(sequence, list) or not sequence:
        raise ValueError(f"Scenario '{scenario_name}' agent '{agent}' must be a non-empty list")

    item = sequence[nth] if nth < len(sequence) else sequence[-1]
    return _response_to_content(item)


class FakeChatOpenAI:
    """Tiny substitute for ChatOpenAI used by workflow tests."""

    def __init__(self, model: str = "fake-model", temperature: float = 0.0, **_: Any) -> None:
        self.model = model
        self.temperature = temperature

    def invoke(self, prompt: str) -> FakeResponse:
        scenario_name = os.getenv("TEACHING_MAP_FAKE_SCENARIO", "all_pass").strip() or "all_pass"
        agent = _detect_agent(prompt)
        content = _pick_response(scenario_name, agent)
        return FakeResponse(content=content)


def reset_runtime_state() -> None:
    with _RUNTIME_LOCK:
        _RUNTIME_STATE["calls"] = {}


def get_call_counters() -> Dict[str, int]:
    with _RUNTIME_LOCK:
        return dict(_RUNTIME_STATE["calls"])


def list_available_scenarios() -> List[str]:
    return sorted(_resolve_scenario_data().keys())
