"""投档引擎总入口（3 号）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .batch import EngineState, run_unified
from .quota import carry_over, run_quota_alloc, run_self_recruit


@dataclass
class RunOutput:
    """引擎首版输出。

    results/logs/leftover 对齐 docs/09；兼容属性供 2 号首版 store/types 对接。
    正式 src.types.RunOutput 合入后，只需要在集成层替换构造方式。
    """

    run_id: str
    results: list[dict]
    logs: list[dict]
    leftover: dict[str, int]
    carry_logs: list[dict] = field(default_factory=list)
    issues: list[Any] = field(default_factory=list)
    modified_plans: list[Any] = field(default_factory=list)

    @property
    def admit_result_rows(self) -> list[dict]:
        return self.results

    @property
    def admit_log_rows(self) -> list[dict]:
        return self.logs

    @property
    def carry_log_rows(self) -> list[dict]:
        return self.carry_logs


def _normalize_batches(batches: Iterable[int]) -> list[int]:
    selected = [int(item) for item in batches]
    if not selected:
        raise ValueError("batches 不能为空")
    if any(item not in (1, 2, 3, 4) for item in selected):
        raise ValueError("批次只能取 1、2、3、4")
    if len(selected) != len(set(selected)):
        raise ValueError("batches 不得重复")
    if selected != sorted(selected):
        raise ValueError("批次必须按 1 -> 2 -> 3 -> 4 顺序传入")
    return selected


def run_batches(
    dataset: Any,
    rules: dict,
    run_id: str,
    batches: Iterable[int],
) -> RunOutput:
    """按给定的升序批次执行一次独立投档。

    本函数不保存跨调用状态；需要完整的跨批次排除与结转时，应在一次调用中
    传入连续批次，或直接调用 run_all。
    """
    selected = _normalize_batches(batches)
    state = EngineState.build(dataset, rules, run_id)

    for batch_no in selected:
        if batch_no == 1:
            run_self_recruit(dataset, rules, state)
            carry_over(state, 1)
        elif batch_no == 2:
            run_quota_alloc(dataset, rules, state)
            carry_over(state, 2)
        elif batch_no in (3, 4):
            run_unified(batch_no, dataset, rules, state)

    return RunOutput(
        run_id=str(run_id),
        results=list(state.results),
        logs=list(state.logs),
        leftover=dict(sorted(state.remaining.items())),
        carry_logs=list(state.carry_logs),
    )


def run_all(dataset: Any, rules: dict, run_id: str) -> RunOutput:
    """严格按第一至第四批执行完整投档。"""
    return run_batches(dataset, rules, run_id, [1, 2, 3, 4])

