"""统计报表组装（4 号：黎俊彤）。

职责：给 1 号报告取数用的“全校与分批汇总”（docs/09 第 3 节 4 号第五行）。
入参：run_id；可选 conn、mock
出参：dict{run, overall, by_batch, by_category, by_school, conservation, notes}

注意：本模块只做汇总与守恒核对（输出参考值），
     正式的口径审计由 1 号的 src/check_metrics.py 负责，两边结论不一致时以 1 号为准。
"""

from __future__ import annotations

import datetime as _dt
import sqlite3

try:
    from src.query import open_cursor, use_mock
    from src.query import mockdata as _mock
    from src.query.stats import _aggregate, _group, _mock_plan_items, _plan_items
except ImportError:
    from query import open_cursor, use_mock
    from query import mockdata as _mock
    from query.stats import _aggregate, _group, _mock_plan_items, _plan_items


def build_stats_report(run_id: str, *, conn=None, mock=None) -> dict:
    """一份可直接贴进报告的全量统计汇总。"""
    mock_mode = use_mock(mock)

    if mock_mode:
        items = _mock_items()
        volunteered_total = len({v["student_id"] for v in _mock.VOLUNTEERS})
        admitted_distinct = len({r["student_id"] for r in _mock.RESULTS})
        run_meta = dict(_mock.RUN_META, run_id=run_id)
    else:
        with open_cursor(conn) as cur:
            items = _db_items(cur, run_id)
            volunteered_total = _distinct_students(cur, "volunteer", None)
            admitted_distinct = _distinct_students(cur, "admit_result", run_id)
            run_meta = _run_meta(cur, run_id)

    overall = _aggregate(items)
    overall.update({
        "volunteered_students": volunteered_total,
        "admitted_students": admitted_distinct,
        "unadmitted_students": max(volunteered_total - admitted_distinct, 0),
        "admit_rate": round(admitted_distinct / volunteered_total, 4) if volunteered_total else 0.0,
    })

    by_batch = [
        dict(batch=b, **_aggregate(v))
        for b, v in sorted(_group(items, "batch").items())
    ]
    by_category = [
        dict(category=c, **_aggregate(v))
        for c, v in sorted(_group(items, "category").items())
    ]
    by_school = []
    for sid, group in sorted(_group(items, "school_id").items()):
        row = {"school_id": sid, "school": group[0]["school_name"]}
        row.update(_aggregate(group))
        by_school.append(row)
    by_school.sort(key=lambda r: (-r["admitted_count"], r["school_id"]))

    return {
        "run_id": run_id,
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "mock": mock_mode,
        "run": run_meta,
        "overall": overall,
        "by_batch": by_batch,
        "by_category": by_category,
        "by_school": by_school,
        "conservation": _conservation(items),
        "notes": [
            "最低录取分＝该计划已录考生总分的最小值（R30）；末位考生＝按录取顺序最后录取者（R31），两者可能不是同一人。",
            "计划无人录取时最低录取分与末位考生为空，界面显示“无”，不得记为 0（R32）。",
            "完成率＝已录人数／有效计划数，有效计划数＝初始计划＋转入（R27）。",
            "学校总体与分批、分类统计分开计算，不混算完成率（R33）。",
            "数据来源：run_id 对应的 admit_result / admit_log / plan / carry_log；口径参数见 config/rules.toml。",
        ],
    }


# ---------------------------------------------------------------- 内部实现

def _db_items(cur: sqlite3.Cursor, run_id: str) -> list[dict]:
    """复用 stats 的行结构，避免第二套口径。"""
    return _plan_items(cur, run_id)


def _mock_items() -> list[dict]:
    return _mock_plan_items()


def _distinct_students(cur: sqlite3.Cursor, table: str, run_id: str | None) -> int:
    """去重考生数；admit_result 按 run_id 过滤，volunteer 不过滤。"""
    try:
        if run_id is None:
            row = cur.execute(f"SELECT COUNT(DISTINCT student_id) AS c FROM {table}").fetchone()
        else:
            row = cur.execute(
                f"SELECT COUNT(DISTINCT student_id) AS c FROM {table} WHERE run_id = ?",
                (run_id,)).fetchone()
        return int(row["c"] or 0)
    except sqlite3.Error:
        return 0


def _run_meta(cur: sqlite3.Cursor, run_id: str) -> dict | None:
    """run 表的运行快照（1 号维护），表不存在时返回 None。"""
    try:
        row = cur.execute(
            "SELECT run_id, year, data_version, operator, created_at FROM run WHERE run_id = ?",
            (run_id,)).fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        return None


def _conservation(items: list[dict]) -> dict:
    """R27：有效计划数 = 已录 + 剩余，逐计划核对，只回报不一致的。"""
    mismatches = []
    for i in items:
        expected = i["quota_total"] - i["admitted_count"]
        if expected != i["remaining"]:
            mismatches.append({
                "plan_id": i["plan_id"], "quota_total": i["quota_total"],
                "admitted_count": i["admitted_count"],
                "remaining": i["remaining"], "expected_remaining": expected,
            })
    return {
        "formula": "quota + carry_in - admitted = remaining（R27）",
        "checked": len(items),
        "mismatch": len(mismatches),
        "items": mismatches[:20],  # 只回前 20 条，全量交 1 号 check_metrics
    }
