"""考生维度查询（4 号：黎俊彤）。

职责：按考生查去向与各志愿处理情况（docs/09 第 3 节 4 号第一行）。
入参：run_id、student_id；可选 conn（复用调用方连接）、mock（强制假数据）
出参：dict，形状见 docs/08_协作规范与样例.md 第 6 节
      {"run_id","student_id","score","tie_seq","admitted","batch","plan_id","school",
       "volunteer_no","admit_order","volunteers":[{batch,seq,plan_id,status,reason_code}]}
说明：
- 只读 student / volunteer / admit_result / admit_log，不推算任何投档规则；
- 未录取时 batch、plan_id、volunteer_no、admit_order 一律 None（不是 0、不是空串）。
"""

from __future__ import annotations

import sqlite3

try:  # 以仓库根为 sys.path 导入（python -m src.query.selfcheck）
    from src.query import open_cursor, use_mock
    from src.query import mockdata as _mock
    from src.query.reasons import describe
except ImportError:  # 以 src 为 sys.path 导入（6 号网关的常见写法）
    from query import open_cursor, use_mock
    from query import mockdata as _mock
    from query.reasons import describe


def get_student_result(run_id: str, student_id: str, *, conn=None, mock=None) -> dict:
    """考生查询：最终去向 + 每个志愿的处理情况。"""
    if use_mock(mock):
        return _mock_student_result(run_id, student_id)

    with open_cursor(conn) as cur:
        stu = cur.execute(
            "SELECT s.student_id, s.name, s.junior_school_id, s.score, s.tie_seq, "
            "       m.name AS junior_school "
            "FROM student s LEFT JOIN middle_school m ON m.school_id = s.junior_school_id "
            "WHERE s.student_id = ?", (student_id,)).fetchone()
        if stu is None:
            return _empty_result(run_id, student_id, exists=False)

        # 录取结果（run_id + 学生唯一，契约表约束）
        res = cur.execute(
            "SELECT r.batch, r.plan_id, r.volunteer_no, r.admit_order, h.name AS school "
            "FROM admit_result r "
            "LEFT JOIN plan p ON p.plan_id = r.plan_id "
            "LEFT JOIN high_school h ON h.school_id = p.high_school_id "
            "WHERE r.run_id = ? AND r.student_id = ?", (run_id, student_id)).fetchone()

        # 志愿表按年份过滤（volunteer 的主键含 year）
        year = _run_year(cur, run_id)
        if year is None:
            vols = cur.execute(
                "SELECT batch, seq, plan_id FROM volunteer WHERE student_id = ? "
                "ORDER BY batch, seq", (student_id,)).fetchall()
        else:
            vols = cur.execute(
                "SELECT batch, seq, plan_id FROM volunteer WHERE student_id = ? AND year = ? "
                "ORDER BY batch, seq", (student_id, year)).fetchall()

        # 日志：按 (batch, plan_id) 取该生在该计划上的判定
        logs = cur.execute(
            "SELECT batch, plan_id, action, reason_code FROM admit_log "
            "WHERE run_id = ? AND student_id = ? ORDER BY batch, log_id",
            (run_id, student_id)).fetchall()
        log_map = {(r["batch"], r["plan_id"]): r for r in logs}

    volunteers = []
    for v in vols:
        key = (v["batch"], v["plan_id"])
        log = log_map.get(key)
        if res is not None and v["plan_id"] == res["plan_id"] and v["batch"] == res["batch"]:
            status, reason = "admitted", None
        elif log is not None and log["action"] == "admit":
            status, reason = "admitted", None
        elif log is not None and log["action"] == "skip":
            status, reason = "skipped", log["reason_code"]
        else:
            status, reason = "pending", None  # 该志愿没有判定记录（未跑到/数据缺失）
        volunteers.append({
            "batch": v["batch"],
            "seq": v["seq"],
            "plan_id": v["plan_id"],
            "status": status,
            "reason_code": reason,
            "reason_text": describe(reason) if reason else None,
        })

    # 顶层未录原因：取最后一个被跳过志愿的原因码（R34 要求可区分 R01—R07）
    top_reason = None
    if res is None:
        for v in reversed(volunteers):
            if v["status"] == "skipped" and v["reason_code"]:
                top_reason = v["reason_code"]
                break

    return {
        "run_id": run_id,
        "student_id": stu["student_id"],
        "exists": True,
        "name": stu["name"],
        "junior_school_id": stu["junior_school_id"],
        "junior_school": stu["junior_school"],
        "score": stu["score"],
        "tie_seq": stu["tie_seq"],
        "admitted": res is not None,
        "batch": res["batch"] if res else None,
        "plan_id": res["plan_id"] if res else None,
        "school": res["school"] if res else None,
        "volunteer_no": res["volunteer_no"] if res else None,
        "admit_order": res["admit_order"] if res else None,
        "reason_code": top_reason,
        "reason_text": describe(top_reason) if top_reason else None,
        "volunteers": volunteers,
    }


def _run_year(cur: sqlite3.Cursor, run_id: str) -> int | None:
    """取 run.year；run 表还没建或没有该运行时返回 None（此时不按年份过滤志愿）。"""
    try:
        row = cur.execute("SELECT year FROM run WHERE run_id = ?", (run_id,)).fetchone()
        return row["year"] if row else None
    except sqlite3.Error:
        return None


def _empty_result(run_id: str, student_id: str, exists: bool = False) -> dict:
    """查不到考生时的稳定返回，6 号据此返回 404。"""
    return {
        "run_id": run_id,
        "student_id": student_id,
        "exists": exists,
        "name": None,
        "junior_school_id": None,
        "junior_school": None,
        "score": None,
        "tie_seq": None,
        "admitted": False,
        "batch": None,
        "plan_id": None,
        "school": None,
        "volunteer_no": None,
        "admit_order": None,
        "reason_code": None,
        "reason_text": None,
        "volunteers": [],
    }


# ---------------------------------------------------------------- mock 分支

def _mock_student_result(run_id: str, student_id: str) -> dict:
    """mock：用 src/query/mockdata.py 的假数据拼出与 DB 分支同形的返回。"""
    stu = _mock.student(student_id)
    if stu is None:
        return _empty_result(run_id, student_id, exists=False)

    res = next((r for r in _mock.RESULTS if r["student_id"] == student_id), None)
    vols = [v for v in _mock.VOLUNTEERS if v["student_id"] == student_id]
    logs = [l for l in _mock.LOGS if l["student_id"] == student_id]
    log_map = {(l["batch"], l["plan_id"]): l for l in logs}

    volunteers = []
    for v in sorted(vols, key=lambda x: (x["batch"], x["seq"])):
        log = log_map.get((v["batch"], v["plan_id"]))
        if res is not None and v["plan_id"] == res["plan_id"] and v["batch"] == res["batch"]:
            status, reason = "admitted", None
        elif log is not None and log["action"] == "admit":
            status, reason = "admitted", None
        elif log is not None and log["action"] == "skip":
            status, reason = "skipped", log["reason_code"]
        else:
            status, reason = "pending", None
        volunteers.append({
            "batch": v["batch"], "seq": v["seq"], "plan_id": v["plan_id"],
            "status": status, "reason_code": reason,
            "reason_text": describe(reason) if reason else None,
        })

    top_reason = None
    if res is None:
        for v in reversed(volunteers):
            if v["status"] == "skipped" and v["reason_code"]:
                top_reason = v["reason_code"]
                break

    school = _mock.school_of_plan(res["plan_id"]) if res else None
    return {
        "run_id": run_id,
        "student_id": student_id,
        "exists": True,
        "name": stu["name"],
        "junior_school_id": stu["junior_school_id"],
        "junior_school": _mock.junior_name(stu["junior_school_id"]),
        "score": stu["score"],
        "tie_seq": stu["tie_seq"],
        "admitted": res is not None,
        "batch": res["batch"] if res else None,
        "plan_id": res["plan_id"] if res else None,
        "school": school["name"] if school else None,
        "volunteer_no": res["volunteer_no"] if res else None,
        "admit_order": res["admit_order"] if res else None,
        "reason_code": top_reason,
        "reason_text": describe(top_reason) if top_reason else None,
        "volunteers": volunteers,
        "_mock": True,
    }
