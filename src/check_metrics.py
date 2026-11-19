"""统计口径与名额守恒自检（1 号）。

职责：跑完一次模拟后，按规则条款对结果做独立审计，输出问题清单；空列表即通过。
覆盖条款：R17（录取唯一）、R18（即时退出）、R26（只转一次）、R27（余额守恒）、
R30—R32（统计口径）、R16（同分序号与志愿序号上限）。

入参：sqlite3 连接、run_id。参数（L、各批志愿上限）从 run.params_json 读取，
      因此审计依据是运行时快照，而不是当前配置。
出参：list[dict]，每项 {table, row, key, code, msg}，与 src/types.Issue 同构。

本模块只读，不改任何表；缺表或缺列一律让 sqlite 抛错，不做兜底。
"""

import json
import sqlite3


def check_run(conn: sqlite3.Connection, run_id: str) -> list:
    """审计一次运行，返回问题清单。"""
    params = _params(conn, run_id)
    control_line = int(params["control_line"])

    issues: list = []
    issues += _check_duplicate_admit(conn, run_id)
    issues += _check_quota(conn, run_id)
    issues += _check_balance(conn, run_id)
    issues += _check_carry_once(conn, run_id)
    issues += _check_admit_order(conn, run_id)
    issues += _check_volunteer_link(conn, run_id)
    issues += _check_score_floor(conn, run_id, control_line)
    issues += _check_volunteer_limit(conn, run_id, params["batch_volunteer_limit"])
    return issues


def _params(conn: sqlite3.Connection, run_id: str) -> dict:
    row = conn.execute(
        "SELECT params_json FROM run WHERE run_id = ?", (run_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"运行不存在: {run_id}")
    return json.loads(row[0])


def _issue(table: str, row, key: str, code: str, msg: str) -> dict:
    return {"table": table, "row": row, "key": key, "code": code, "msg": msg}


def _check_duplicate_admit(conn: sqlite3.Connection, run_id: str) -> list:
    """R17：每生每次运行最多一条录取记录。"""
    rows = conn.execute(
        "SELECT student_id, COUNT(*) AS n FROM admit_result"
        " WHERE run_id = ? GROUP BY student_id HAVING n > 1",
        (run_id,),
    ).fetchall()
    return [
        _issue("admit_result", r[1], r[0], "DUPLICATE_ADMIT", f"考生 {r[0]} 被录取 {r[1]} 次")
        for r in rows
    ]


def _effective_quota_sql() -> str:
    return (
        "SELECT r.plan_id AS plan_id, COUNT(*) AS admitted,"
        "       p.quota AS quota, COALESCE(c.in_amt, 0) AS carried_in,"
        "       p.remaining AS remaining"
        " FROM admit_result r"
        " JOIN plan p ON p.plan_id = r.plan_id"
        " LEFT JOIN ("
        "   SELECT to_plan_id, SUM(amount) AS in_amt FROM carry_log"
        "   WHERE run_id = ? GROUP BY to_plan_id"
        " ) c ON c.to_plan_id = r.plan_id"
        " WHERE r.run_id = ?"
        " GROUP BY r.plan_id"
    )


def _check_quota(conn: sqlite3.Connection, run_id: str) -> list:
    """R17：录取数不得超过有效名额（初始 + 转入）。"""
    rows = conn.execute(_effective_quota_sql(), (run_id, run_id)).fetchall()
    issues = []
    for plan_id, admitted, quota, carried_in, _remaining in rows:
        effective = quota + carried_in
        if admitted > effective:
            issues.append(
                _issue(
                    "plan", admitted, plan_id, "OVER_QUOTA",
                    f"计划 {plan_id} 录 {admitted} 人，超过有效名额 {effective}"
                    f"（初始 {quota} + 转入 {carried_in}）",
                )
            )
    return issues


def _check_balance(conn: sqlite3.Connection, run_id: str) -> list:
    """R27：初始计划 + 转入 = 已录 + 剩余。"""
    rows = conn.execute(_effective_quota_sql(), (run_id, run_id)).fetchall()
    issues = []
    for plan_id, admitted, quota, carried_in, remaining in rows:
        effective = quota + carried_in
        if effective != admitted + remaining:
            issues.append(
                _issue(
                    "plan", admitted, plan_id, "BALANCE_MISMATCH",
                    f"计划 {plan_id} 有效名额 {effective} ≠ 已录 {admitted} + 剩余 {remaining}",
                )
            )
    return issues


def _check_carry_once(conn: sqlite3.Connection, run_id: str) -> list:
    """R26：每个目标计划只允许一次结转。"""
    rows = conn.execute(
        "SELECT to_plan_id, COUNT(*) AS n FROM carry_log"
        " WHERE run_id = ? GROUP BY to_plan_id HAVING n > 1",
        (run_id,),
    ).fetchall()
    return [
        _issue("carry_log", r[1], r[0], "REPEATED_CARRY", f"计划 {r[0]} 结转了 {r[1]} 次")
        for r in rows
    ]


def _check_admit_order(conn: sqlite3.Connection, run_id: str) -> list:
    """R31：录取顺序须从 1 开始连续编号，末位考生才有定义。"""
    rows = conn.execute(
        "SELECT plan_id, MIN(admit_order), MAX(admit_order), COUNT(*)"
        " FROM admit_result WHERE run_id = ? GROUP BY plan_id",
        (run_id,),
    ).fetchall()
    issues = []
    for plan_id, low, high, count in rows:
        if low != 1 or high != count:
            issues.append(
                _issue(
                    "admit_result", count, plan_id, "ADMIT_ORDER_GAP",
                    f"计划 {plan_id} 的录取顺序为 {low}—{high}，共 {count} 条，编号不连续",
                )
            )
    return issues


def _check_volunteer_link(conn: sqlite3.Connection, run_id: str) -> list:
    """R18：每条录取须对应一条有效的志愿记录。"""
    rows = conn.execute(
        "SELECT r.student_id, r.batch, r.volunteer_no, r.plan_id FROM admit_result r"
        " JOIN run u ON u.run_id = r.run_id"
        " LEFT JOIN volunteer v"
        "   ON v.year = u.year AND v.student_id = r.student_id"
        "  AND v.batch = r.batch AND v.seq = r.volunteer_no AND v.plan_id = r.plan_id"
        " WHERE r.run_id = ? AND v.student_id IS NULL",
        (run_id,),
    ).fetchall()
    return [
        _issue(
            "admit_result", r[2], r[0], "MISSING_VOLUNTEER",
            f"考生 {r[0]} 的录取无对应志愿（批次 {r[1]} 志愿 {r[2]} 计划 {r[3]}）",
        )
        for r in rows
    ]


def _check_score_floor(conn: sqlite3.Connection, run_id: str, control_line: int) -> list:
    """R9、R10：录取分数不得低于计划控制线与 L 中的较高者。"""
    rows = conn.execute(
        "SELECT r.student_id, r.score, p.plan_id, p.control_line"
        " FROM admit_result r JOIN plan p ON p.plan_id = r.plan_id"
        " WHERE r.run_id = ?",
        (run_id,),
    ).fetchall()
    issues = []
    for student_id, score, plan_id, plan_line in rows:
        floor = max(int(plan_line or 0), int(control_line))
        if score < floor:
            issues.append(
                _issue(
                    "admit_result", score, student_id, "BELOW_CONTROL",
                    f"考生 {student_id} 以 {score} 分录取计划 {plan_id}，低于门槛 {floor}",
                )
            )
    return issues


def _check_volunteer_limit(conn: sqlite3.Connection, run_id: str, limits: dict) -> list:
    """R7：被录志愿序号不得超过该批上限。"""
    rows = conn.execute(
        "SELECT student_id, batch, volunteer_no FROM admit_result WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    issues = []
    for student_id, batch, volunteer_no in rows:
        limit = int(limits.get(f"batch{batch}", 0))
        if limit and volunteer_no > limit:
            issues.append(
                _issue(
                    "admit_result", volunteer_no, student_id, "VOLUNTEER_OVER_LIMIT",
                    f"考生 {student_id} 的批次 {batch} 志愿 {volunteer_no} 超过上限 {limit}",
                )
            )
    return issues
