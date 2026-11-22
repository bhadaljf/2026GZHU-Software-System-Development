"""统招批次执行器与引擎内部状态（3 号）。

职责：实现第三、四批的“批次 -> 梯度 -> 志愿 -> 计划 -> 考生”循环，
并集中维护录取唯一性、计划余额、录取顺序和投档日志。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .bands import assign_band


def value(row: Any, name: str, default: Any = None) -> Any:
    """同时读取 dict 与 dataclass/普通对象字段。"""
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def rows(dataset: Any, *names: str) -> list[Any]:
    """从数据集中读取第一个存在的集合字段。"""
    for name in names:
        found = value(dataset, name, None)
        if found is not None:
            return list(found)
    return []


@dataclass
class BatchOutcome:
    """单批执行结果；明细仍保存在共享 EngineState 中。"""

    admitted: int = 0
    skipped: int = 0
    leftover: dict[str, int] = field(default_factory=dict)


@dataclass
class EngineState:
    """单次运行内部状态，不跨运行复用，也不修改输入 Dataset。"""

    dataset: Any
    rules: dict
    run_id: str
    students: list[Any]
    plans: list[Any]
    volunteers: list[Any]
    quota_plans: list[Any]
    eligibility: list[Any]
    student_by_id: dict[str, Any]
    plan_by_id: dict[str, Any]
    remaining: dict[str, int]
    quota_remaining: dict[tuple[str, str], int]
    admitted_students: set[str] = field(default_factory=set)
    results: list[dict] = field(default_factory=list)
    logs: list[dict] = field(default_factory=list)
    carry_logs: list[dict] = field(default_factory=list)
    plan_orders: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    carried: set[tuple[int, str]] = field(default_factory=set)

    @classmethod
    def build(cls, dataset: Any, rules: dict, run_id: str) -> "EngineState":
        students = rows(dataset, "students")
        plans = rows(dataset, "plans")
        volunteers = rows(dataset, "volunteers")
        quota_plans = rows(dataset, "quota_plans")
        eligibility = rows(
            dataset, "eligibility", "self_recruit_eligibilities"
        )

        student_by_id = {
            str(value(item, "student_id")): item for item in students
        }
        plan_by_id = {str(value(item, "plan_id")): item for item in plans}
        remaining = {
            plan_id: int(value(item, "remaining", value(item, "quota", 0)))
            for plan_id, item in plan_by_id.items()
        }
        quota_remaining = {
            (str(value(item, "plan_id")), str(value(item, "junior_school_id"))):
            int(value(item, "remaining", value(item, "quota", 0)))
            for item in quota_plans
        }

        return cls(
            dataset=dataset,
            rules=rules,
            run_id=str(run_id),
            students=students,
            plans=plans,
            volunteers=volunteers,
            quota_plans=quota_plans,
            eligibility=eligibility,
            student_by_id=student_by_id,
            plan_by_id=plan_by_id,
            remaining=remaining,
            quota_remaining=quota_remaining,
        )

    def add_log(
        self,
        *,
        batch: int,
        band: int,
        volunteer_no: int | None,
        plan_id: str | None,
        student_id: str | None,
        action: str,
        reason_code: str | None,
        balance_before: int | None,
        balance_after: int | None,
        note: str | None = None,
    ) -> None:
        index = len(self.logs) + 1
        self.logs.append(
            {
                "log_id": f"{self.run_id}-L{index:08d}",
                "run_id": self.run_id,
                "batch": int(batch),
                "band": int(band),
                "volunteer_no": volunteer_no,
                "plan_id": plan_id,
                "student_id": student_id,
                "action": action,
                "reason_code": reason_code,
                "balance_before": balance_before,
                "balance_after": balance_after,
                "note": note,
            }
        )

    def admit(
        self,
        *,
        student: Any,
        plan: Any,
        batch: int,
        band: int,
        volunteer_no: int,
        pool_key: tuple[str, str] | None = None,
    ) -> bool:
        """录取一名考生并原子更新内存余额；余额不足时返回 False。"""
        student_id = str(value(student, "student_id"))
        plan_id = str(value(plan, "plan_id"))
        if student_id in self.admitted_students:
            return False

        before = (
            self.quota_remaining.get(pool_key, 0)
            if pool_key is not None
            else self.remaining.get(plan_id, 0)
        )
        if before <= 0:
            return False

        if pool_key is not None:
            self.quota_remaining[pool_key] = before - 1
            self.remaining[plan_id] = max(0, self.remaining.get(plan_id, 0) - 1)
        else:
            self.remaining[plan_id] = before - 1

        self.admitted_students.add(student_id)
        self.plan_orders[plan_id] += 1
        order = self.plan_orders[plan_id]
        result_id = f"{self.run_id}-{batch}-{plan_id}-{order}"
        self.results.append(
            {
                "result_id": result_id,
                "run_id": self.run_id,
                "student_id": student_id,
                "plan_id": plan_id,
                "batch": int(batch),
                "score": int(value(student, "score")),
                "tie_seq": int(value(student, "tie_seq")),
                "volunteer_no": int(volunteer_no),
                "admit_order": order,
            }
        )
        self.add_log(
            batch=batch,
            band=band,
            volunteer_no=volunteer_no,
            plan_id=plan_id,
            student_id=student_id,
            action="admit",
            reason_code=None,
            balance_before=before,
            balance_after=before - 1,
        )
        return True


def _candidate_sort_key(state: EngineState, volunteer: Any) -> tuple[int, int, str]:
    student_id = str(value(volunteer, "student_id"))
    student = state.student_by_id[student_id]
    return (
        -int(value(student, "score")),
        int(value(student, "tie_seq")),
        student_id,
    )


def _skip(
    state: EngineState,
    volunteer: Any,
    *,
    batch: int,
    band: int,
    reason: str,
    balance: int | None,
    note: str | None = None,
) -> None:
    state.add_log(
        batch=batch,
        band=band,
        volunteer_no=int(value(volunteer, "seq", 0)) or None,
        plan_id=str(value(volunteer, "plan_id", "")) or None,
        student_id=str(value(volunteer, "student_id", "")) or None,
        action="skip",
        reason_code=reason,
        balance_before=balance,
        balance_after=balance,
        note=note,
    )


def run_unified(
    batch_no: int,
    dataset: Any,
    rules: dict,
    state: EngineState,
) -> BatchOutcome:
    """执行第三或第四批统招。"""
    if batch_no not in (3, 4):
        raise ValueError("run_unified 只接受第三或第四批")

    before_results = len(state.results)
    before_logs = len(state.logs)
    batch_volunteers = [
        item
        for item in state.volunteers
        if int(value(item, "batch", 0)) == batch_no
    ]
    limit = int(rules["batch_volunteer_limit"][f"batch{batch_no}"])
    last_band = assign_band(int(rules["control_line"]), rules)

    for band in range(0, last_band + 1):
        if band == 0:
            seq_values: Iterable[int] = range(1, limit + 1)
        else:
            seq_values = range(1, limit + 1)

        for seq in seq_values:
            current = []
            for volunteer in batch_volunteers:
                if int(value(volunteer, "seq", 0)) != seq:
                    continue
                student = state.student_by_id.get(str(value(volunteer, "student_id")))
                student_band = (
                    assign_band(int(value(student, "score")), rules)
                    if student is not None
                    else 0
                )
                if student_band == band:
                    current.append(volunteer)

            grouped: dict[str, list[Any]] = defaultdict(list)
            for volunteer in current:
                grouped[str(value(volunteer, "plan_id", ""))].append(volunteer)

            for plan_id in sorted(grouped):
                plan = state.plan_by_id.get(plan_id)
                candidates = grouped[plan_id]
                if plan is None or int(value(plan, "batch", 0)) != batch_no:
                    for volunteer in candidates:
                        _skip(
                            state,
                            volunteer,
                            batch=batch_no,
                            band=band,
                            reason="R06",
                            balance=None,
                            note="志愿引用的计划不存在或批次不匹配",
                        )
                    continue
                if str(value(plan, "category")) != "unified":
                    for volunteer in candidates:
                        _skip(
                            state,
                            volunteer,
                            batch=batch_no,
                            band=band,
                            reason="R06",
                            balance=state.remaining.get(plan_id, 0),
                            note="统招执行器收到非统招计划",
                        )
                    continue

                valid = [
                    item
                    for item in candidates
                    if str(value(item, "student_id")) in state.student_by_id
                ]
                invalid = [item for item in candidates if item not in valid]
                for volunteer in invalid:
                    _skip(
                        state,
                        volunteer,
                        batch=batch_no,
                        band=band,
                        reason="R06",
                        balance=state.remaining.get(plan_id, 0),
                        note="考生不存在",
                    )

                for volunteer in sorted(valid, key=lambda x: _candidate_sort_key(state, x)):
                    student_id = str(value(volunteer, "student_id"))
                    student = state.student_by_id[student_id]
                    balance = state.remaining.get(plan_id, 0)
                    if student_id in state.admitted_students:
                        _skip(state, volunteer, batch=batch_no, band=band, reason="R04", balance=balance)
                    elif band == 0 or int(value(student, "score")) < max(
                        int(rules["control_line"]), int(value(plan, "control_line", 0))
                    ):
                        _skip(state, volunteer, batch=batch_no, band=band, reason="R01", balance=balance)
                    elif balance <= 0:
                        _skip(state, volunteer, batch=batch_no, band=band, reason="R02", balance=balance)
                    else:
                        state.admit(
                            student=student,
                            plan=plan,
                            batch=batch_no,
                            band=band,
                            volunteer_no=seq,
                        )

    affected = {
        str(value(plan, "plan_id")): state.remaining[str(value(plan, "plan_id"))]
        for plan in state.plans
        if int(value(plan, "batch", 0)) == batch_no
    }
    admitted = len(state.results) - before_results
    new_logs = state.logs[before_logs:]
    return BatchOutcome(
        admitted=admitted,
        skipped=sum(1 for item in new_logs if item["action"] == "skip"),
        leftover=affected,
    )

