"""Shared state schema for the LangGraph teaching map workflow."""
from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict


def _reset_or_append(existing: list, new: list) -> list:
    """自定义 reducer：bump_retry 节点传入空列表时清空旧结果，否则追加。"""
    if not new:
        return []
    return existing + new


def _reset_or_add(existing: int, new: int) -> int:
    """自定义 reducer：传入负数时重置为 0，否则累加。"""
    if new < 0:
        return 0
    return existing + new


class Question(TypedDict, total=False):
    id: str
    content: str
    question_type: str
    knowledge_points: List[str]
    cognitive_level: str
    difficulty: float
    parent_id: Optional[str]


class Edge(TypedDict, total=False):
    source: str
    target: str
    relation: str
    weight: float


class ValidationResult(TypedDict, total=False):
    validator: str
    passed: bool
    feedback: str


class TeachingMap(TypedDict, total=False):
    nodes: List[Question]
    edges: List[Edge]


class GraphState(TypedDict, total=False):
    subject: str
    grade: str
    teaching_goals: str
    student_profile: str
    language_style: str
    attachment: str

    analysis_result: Dict[str, Any]
    map_construction_logic: Dict[str, Any]
    main_questions: List[Question]
    variant_questions: List[Question]
    scaffold_questions: List[Question]

    # 并行分支结果自动追加；bump_retry 节点传入空列表时触发清空
    validation_results: Annotated[List[ValidationResult], _reset_or_append]
    main_retry_count: int
    variant_retry_count: int
    scaffold_retry_count: int

    # 专用 feedback 暂存字段，bump_retry 在清空 validation_results 前先把反馈存入，
    # 供对应生成器下一轮读取
    main_validation_feedback: List[ValidationResult]
    main_failed_validators: List[str]
    variant_validation_feedback: List[ValidationResult]
    scaffold_validation_feedback: List[ValidationResult]

    # 主干问题并行检验完成计数（累加，扇入节点传入 -999 触发重置为 0）
    main_checks_done: Annotated[int, _reset_or_add]
    # 本轮主干检验期望到达数量
    main_checks_expected: int

    # 变式/支架两条流水线完成计数（累加，aggregate 节点传入 -999 重置）
    sub_pipelines_done: Annotated[int, _reset_or_add]

    teaching_map: TeachingMap

    progress_messages: Annotated[List[str], operator.add]
