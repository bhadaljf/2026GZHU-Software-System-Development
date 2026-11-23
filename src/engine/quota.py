"""自主招生、名额分配与结转（3 号）。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .bands import assign_band
from .batch import BatchOutcome, EngineState, _candidate_sort_key, _skip, value


VALID_ELIGIBILITY = {"ok", "valid", "eligible", "1", "true"}


def _is_eligible(status: Any) -> bool:
    if isinstance(status, bool):
        return status
    return str(status).strip().lower() in VALID_ELIGIBILITY


def run_self_recruit(
    dataset: Any,
    rules: dict,
    state: EngineState,
) -> BatchOutcome:
    """执行第一批自主招生：资格、控制线、考核排名。"""
    before_results = len(state.results)
    before_logs = len(state.logs)
    eligibility = {
        (str(value(item, "student_id")), str(value(item, "high_school_id"))): item
        for item in state.eligibility
    }
    grouped: dict[str, list[Any]] = defaultdict(list)
    for volunteer in state.volunteers:
        if int(value(volunteer, "batch", 0)) == 1:
            grouped[str(value(volunteer, "plan_id", ""))].append(volunteer)

    for plan_id in sorted(grouped):
        plan = state.plan_by_id.get(plan_id)
        volunteers = grouped[plan_id]
        if plan is None or int(value(plan, "batch", 0)) != 1 or str(value(plan, "category")) != "self_recruit":
            for volunteer in volunteers:
                _skip(state, volunteer, batch=1, band=0, reason="R06", balance=None)
            continue

        high_school_id = str(value(plan, "high_school_id"))

        def rank_key(volunteer: Any) -> tuple[int, str]:
            student_id = str(value(volunteer, "student_id"))
            item = eligibility.get((student_id, high_school_id))
            rank = int(value(item, "rank", 2**31 - 1)) if item is not None else 2**31 - 1
            return rank, student_id

        for volunteer in sorted(volunteers, key=rank_key):
            student_id = str(value(volunteer, "student_id"))
            student = state.student_by_id.get(student_id)
            balance = state.remaining.get(plan_id, 0)
            band = assign_band(int(value(student, "score", -1)), rules) if student is not None else 0
            item = eligibility.get((student_id, high_school_id))

            if student is None:
                _skip(state, volunteer, batch=1, band=0, reason="R06", balance=balance)
            elif student_id in state.admitted_students:
                _skip(state, volunteer, batch=1, band=band, reason="R04", balance=balance)
            elif item is None or not _is_eligible(value(item, "status")):
                _skip(state, volunteer, batch=1, band=band, reason="R03", balance=balance)
            elif int(value(student, "score")) < max(
                int(rules["control_line"]), int(value(plan, "control_line", 0))
            ):
                _skip(state, volunteer, batch=1, band=band, reason="R01", balance=balance)
            elif balance <= 0:
                _skip(state, volunteer, batch=1, band=band, reason="R02", balance=balance)
            else:
                state.admit(
                    student=student,
                    plan=plan,
                    batch=1,
                    band=band,
                    volunteer_no=int(value(volunteer, "seq", 1)),
                )

    admitted = len(state.results) - before_results
    new_logs = state.logs[before_logs:]
    return BatchOutcome(
        admitted=admitted,
        skipped=sum(1 for item in new_logs if item["action"] == "skip"),
        leftover={
            plan_id: state.remaining[plan_id]
            for plan_id, plan in state.plan_by_id.items()
            if int(value(plan, "batch", 0)) == 1
        },
    )


def run_quota_alloc(
    dataset: Any,
    rules: dict,
    state: EngineState,
) -> BatchOutcome:
    """执行第二批名额分配，名额池按“高中计划 + 初中”隔离。"""
    before_results = len(state.results)
    before_logs = len(state.logs)
    limit = int(rules["batch_volunteer_limit"]["batch2"])
    last_band = assign_band(int(rules["control_line"]), rules)
    batch_volunteers = [
        item for item in state.volunteers if int(value(item, "batch", 0)) == 2
    ]

    for band in range(0, last_band + 1):
        for seq in range(1, limit + 1):
            grouped: dict[tuple[str, str], list[Any]] = defaultdict(list)
            for volunteer in batch_volunteers:
                if int(value(volunteer, "seq", 0)) != seq:
                    continue
                student_id = str(value(volunteer, "student_id"))
                student = state.student_by_id.get(student_id)
                student_band = assign_band(int(value(student, "score")), rules) if student is not None else 0
                if student_band != band:
                    continue
                school_id = str(value(student, "junior_school_id", "")) if student is not None else ""
                grouped[(str(value(volunteer, "plan_id", "")), school_id)].append(volunteer)

            for pool_key in sorted(grouped):
                plan_id, school_id = pool_key
                plan = state.plan_by_id.get(plan_id)
                volunteers = grouped[pool_key]
                if plan is None or int(value(plan, "batch", 0)) != 2 or str(value(plan, "category")) != "quota":
                    for volunteer in volunteers:
                        _skip(state, volunteer, batch=2, band=band, reason="R06", balance=None)
                    continue
                if pool_key not in state.quota_remaining:
                    for volunteer in volunteers:
                        _skip(
                            state,
                            volunteer,
                            batch=2,
                            band=band,
                            reason="R05",
                            balance=0,
                            note=f"所属初中 {school_id} 没有该计划名额",
                        )
                    continue

                valid = [
                    item
                    for item in volunteers
                    if str(value(item, "student_id")) in state.student_by_id
                ]
                invalid = [item for item in volunteers if item not in valid]
                for volunteer in invalid:
                    _skip(state, volunteer, batch=2, band=band, reason="R06", balance=None)

                for volunteer in sorted(valid, key=lambda x: _candidate_sort_key(state, x)):
                    student_id = str(value(volunteer, "student_id"))
                    student = state.student_by_id[student_id]
                    balance = state.quota_remaining.get(pool_key, 0)
                    if student_id in state.admitted_students:
                        _skip(state, volunteer, batch=2, band=band, reason="R04", balance=balance)
                    elif band == 0 or int(value(student, "score")) < max(
                        int(rules["control_line"]), int(value(plan, "control_line", 0))
                    ):
                        _skip(state, volunteer, batch=2, band=band, reason="R01", balance=balance)
                    elif balance <= 0:
                        _skip(state, volunteer, batch=2, band=band, reason="R02", balance=balance)
                    else:
                        state.admit(
                            student=student,
                            plan=plan,
                            batch=2,
                            band=band,
                            volunteer_no=seq,
                            pool_key=pool_key,
                        )

    admitted = len(state.results) - before_results
    new_logs = state.logs[before_logs:]
    return BatchOutcome(
        admitted=admitted,
        skipped=sum(1 for item in new_logs if item["action"] == "skip"),
        leftover={f"{pid}:{sid}": amount for (pid, sid), amount in state.quota_remaining.items()},
    )


def carry_over(state: EngineState, from_batch: int) -> list[dict]:
    """把第一或第二批余额一次性结转到同校第三批统招计划。"""
    if from_batch not in (1, 2):
        raise ValueError("只允许结转第一或第二批")

    targets = {
        str(value(plan, "high_school_id")): str(value(plan, "plan_id"))
        for plan in state.plans
        if int(value(plan, "batch", 0)) == 3 and str(value(plan, "category")) == "unified"
    }
    grouped: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for plan in state.plans:
        if int(value(plan, "batch", 0)) != from_batch:
            continue
        source_id = str(value(plan, "plan_id"))
        high_school_id = str(value(plan, "high_school_id"))
        target_id = targets.get(high_school_id)
        if target_id is None:
            raise ValueError(f"高中 {high_school_id} 缺少第三批统招接收计划")

        if from_batch == 1:
            amount = state.remaining.get(source_id, 0)
            state.remaining[source_id] = 0
        else:
            pool_keys = [key for key in state.quota_remaining if key[0] == source_id]
            amount = sum(state.quota_remaining[key] for key in pool_keys)
            for key in pool_keys:
                state.quota_remaining[key] = 0
            state.remaining[source_id] = 0
        grouped[target_id].append((source_id, amount))

    created: list[dict] = []
    for target_id in sorted(grouped):
        key = (from_batch, target_id)
        if key in state.carried:
            continue
        state.carried.add(key)
        sources = grouped[target_id]
        amount = sum(item[1] for item in sources)
        if amount <= 0:
            continue
        state.remaining[target_id] = state.remaining.get(target_id, 0) + amount
        index = len(state.carry_logs) + 1
        target = state.plan_by_id[target_id]
        row = {
            "carry_id": f"{state.run_id}-C{index:04d}",
            "run_id": state.run_id,
            "from_batch": from_batch,
            "to_plan_id": target_id,
            "high_school_id": str(value(target, "high_school_id")),
            "amount": amount,
            "source_note": ", ".join(f"{pid}:{num}" for pid, num in sources),
        }
        state.carry_logs.append(row)
        created.append(row)
    return created

