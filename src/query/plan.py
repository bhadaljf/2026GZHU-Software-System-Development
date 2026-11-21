"""计划维度查询（4 号：黎俊彤）。

职责：按高中/计划查录取名单与余额（docs/09 第 3 节 4 号第二行）。
入参：run_id、plan_id、page（从 1 开始）、size（每页条数，1—500）
出参：dict
      {"plan_id","quota","quota_total","admitted_count","remaining","min_score",
       "last_admitted","items","page","size","total","total_pages"}

口径硬约束（R30/R31/R32，写错会被 1 号与 5 号打回）：
- min_score = 该计划已录考生总分的最小值；
- last_admitted = 按 admit_order 最大的那位（末位考生），另报总分、志愿序号、同分序号；
- 两者分别计算，可能不是同一人；
- 无人录取时 min_score 与 last_admitted 都返回 None，界面由 6 号显示“无”，禁止填 0。
"""

from __future__ import annotations

import math
import sqlite3

try:
    from src.query import open_cursor, use_mock
    from src.query import mockdata as _mock
except ImportError:
    from query import open_cursor, use_mock
    from query import mockdata as _mock


MAX_PAGE_SIZE = 500


def get_plan_admissions(run_id: str, plan_id: str, page: int = 1, size: int = 100,
                        *, conn=None, mock=None) -> dict:
    """计划录取名单（分页）+ 余额 + 最低录取分 + 末位考生。"""
    page = max(int(page or 1), 1)
    size = min(max(int(size or 100), 1), MAX_PAGE_SIZE)

    if use_mock(mock):
        return _mock_plan_admissions(run_id, plan_id, page, size)

    with open_cursor(conn) as cur:
        p = cur.execute(
            "SELECT p.plan_id, p.batch, p.category, p.quota, p.remaining, p.control_line, "
            "       h.name AS school "
            "FROM plan p LEFT JOIN high_school h ON h.school_id = p.high_school_id "
            "WHERE p.plan_id = ?", (plan_id,)).fetchone()
        if p is None:
            return _empty_plan(plan_id, page, size, exists=False)

        carry_in = _carry_in(cur, run_id, plan_id)

        agg = cur.execute(
            "SELECT COUNT(*) AS cnt, MIN(score) AS min_score, MAX(score) AS max_score "
            "FROM admit_result WHERE run_id = ? AND plan_id = ?",
            (run_id, plan_id)).fetchone()
        admitted = int(agg["cnt"] or 0)

        last = cur.execute(
            "SELECT student_id, score, tie_seq, volunteer_no, admit_order "
            "FROM admit_result WHERE run_id = ? AND plan_id = ? "
            "ORDER BY admit_order DESC LIMIT 1", (run_id, plan_id)).fetchone()

        rows = cur.execute(
            "SELECT admit_order, student_id, score, tie_seq, volunteer_no "
            "FROM admit_result WHERE run_id = ? AND plan_id = ? "
            "ORDER BY admit_order LIMIT ? OFFSET ?",
            (run_id, plan_id, size, (page - 1) * size)).fetchall()

    quota = int(p["quota"] or 0)
    quota_total = quota + carry_in
    # 契约 R29：plan.remaining 由引擎实时维护；缺失时才用“有效计划数 − 已录”兜底
    remaining = p["remaining"] if p["remaining"] is not None else (quota_total - admitted)

    return {
        "plan_id": p["plan_id"],
        "exists": True,
        "school": p["school"],
        "batch": p["batch"],
        "category": p["category"],
        "control_line": p["control_line"],
        "quota": quota,
        "carry_in": carry_in,
        "quota_total": quota_total,
        "admitted_count": admitted,
        "remaining": int(remaining),
        # R30：最低录取分，独立计算；无人录取为 None
        "min_score": agg["min_score"],
        "max_score": agg["max_score"],
        # R31：末位考生，按录取顺序取最后一位，与 min_score 可以为不同人
        "last_admitted": {
            "student_id": last["student_id"],
            "score": last["score"],
            "tie_seq": last["tie_seq"],
            "volunteer_no": last["volunteer_no"],
            "admit_order": last["admit_order"],
        } if last else None,
        "items": [
            {
                "admit_order": r["admit_order"],
                "student_id": r["student_id"],
                "score": r["score"],
                "tie_seq": r["tie_seq"],
                "volunteer_no": r["volunteer_no"],
            } for r in rows
        ],
        "page": page,
        "size": size,
        "total": admitted,
        "total_pages": max(math.ceil(admitted / size), 1),
    }


def _carry_in(cur: sqlite3.Cursor, run_id: str, plan_id: str) -> int:
    """该计划从上一批转入的名额（R27 有效计划数 = 初始计划 + 转入）。"""
    try:
        row = cur.execute(
            "SELECT COALESCE(SUM(amount), 0) AS amt FROM carry_log "
            "WHERE run_id = ? AND to_plan_id = ?", (run_id, plan_id)).fetchone()
        return int(row["amt"] or 0)
    except sqlite3.Error:
        return 0


def _empty_plan(plan_id: str, page: int, size: int, exists: bool = False) -> dict:
    """计划不存在时的稳定返回，6 号据此返回 404。"""
    return {
        "plan_id": plan_id, "exists": exists, "school": None, "batch": None,
        "category": None, "control_line": None, "quota": None, "carry_in": 0,
        "quota_total": None, "admitted_count": 0, "remaining": None,
        "min_score": None, "max_score": None, "last_admitted": None,
        "items": [], "page": page, "size": size, "total": 0, "total_pages": 1,
    }


# ---------------------------------------------------------------- mock 分支

def _mock_plan_admissions(run_id: str, plan_id: str, page: int, size: int) -> dict:
    """mock：用假数据算同样的口径，验证“最低分 ≠ 末位考生”与“无”的返回。"""
    p = _mock.plan(plan_id)
    if p is None:
        return _empty_plan(plan_id, page, size, exists=False)

    school = _mock.school_of_plan(plan_id)
    rows = sorted([r for r in _mock.RESULTS if r["plan_id"] == plan_id],
                  key=lambda r: r["admit_order"])
    quota = int(p["quota"])
    quota_total = quota  # mock 无结转
    admitted = len(rows)
    min_score = min((r["score"] for r in rows), default=None)
    max_score = max((r["score"] for r in rows), default=None)
    last = rows[-1] if rows else None

    start = (page - 1) * size
    return {
        "plan_id": plan_id,
        "exists": True,
        "school": school["name"] if school else None,
        "batch": p["batch"],
        "category": p["category"],
        "control_line": p["control_line"],
        "quota": quota,
        "carry_in": 0,
        "quota_total": quota_total,
        "admitted_count": admitted,
        "remaining": int(p["remaining"]),
        "min_score": min_score,
        "max_score": max_score,
        "last_admitted": {
            "student_id": last["student_id"], "score": last["score"],
            "tie_seq": last["tie_seq"], "volunteer_no": last["volunteer_no"],
            "admit_order": last["admit_order"],
        } if last else None,
        "items": [
            {"admit_order": r["admit_order"], "student_id": r["student_id"],
             "score": r["score"], "tie_seq": r["tie_seq"], "volunteer_no": r["volunteer_no"]}
            for r in rows[start:start + size]
        ],
        "page": page,
        "size": size,
        "total": admitted,
        "total_pages": max(math.ceil(admitted / size), 1),
        "_mock": True,
    }
