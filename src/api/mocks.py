"""接口假数据（6 号，仅开发/演示用）。

字段形状严格对齐 4 号 `docs/04_接口与统计口径.md` 第 3 节：
- 考生：exists/name/junior_school/reason_text/volunteers[].reason_text，状态含 pending；
- 计划：exists/school/batch/category/control_line/carry_in/quota_total/max_score/total_pages；
- 批次统计：completion_rate/completion_rate_text/unadmitted_students/plans[]；
- 学校统计：school/overall/by_batch/by_category/plans[] 嵌套；
- 分布：bucket_size/buckets[].low/high/lines。

开关：环境变量 ``API_MOCK=1``；默认关闭，真实模式不会回退到本模块。
案例对比固定两个 run_id：RUN20261121-01（调整前）/ RUN20261121-02（调整后）。
"""

from __future__ import annotations

import csv
import io
import math
import os

MOCK = os.getenv("API_MOCK", "0") == "1"

RUN_BEFORE = "RUN20261121-01"
RUN_AFTER = "RUN20261121-02"

REASONS = [
    {"code": "R01", "text": "未达计划控制线或最低控制线", "batches": [1, 2, 3, 4]},
    {"code": "R02", "text": "计划名额已满", "batches": [1, 2, 3, 4]},
    {"code": "R03", "text": "不在自主招生资格名单或排名不达", "batches": [1]},
    {"code": "R04", "text": "前批已录取", "batches": [2, 3, 4]},
    {"code": "R05", "text": "非所属初中名额", "batches": [2]},
    {"code": "R06", "text": "志愿或计划无效", "batches": [1, 2, 3, 4]},
    {"code": "R07", "text": "未填报该计划", "batches": [1, 2, 3, 4]},
]
_REASON_TEXT = {r["code"]: r["text"] for r in REASONS}


def _reason_text(code: str | None) -> str | None:
    if not code:
        return None
    return _REASON_TEXT.get(code, "未知原因")


JUNIOR_SCHOOLS = {"M01": "M 一中", "M02": "M 二中", "M03": "M 三中"}

SCHOOLS = {
    "H01": {"school_id": "H01", "name": "A 校", "recruit_batch": 3},
    "H02": {"school_id": "H02", "name": "B 校", "recruit_batch": 3},
    "H03": {"school_id": "H03", "name": "C 校", "recruit_batch": 4},
}

STUDENTS = {
    "S01": {"student_id": "S01", "name": "甲", "junior_school_id": "M01", "score": 690, "tie_seq": 1},
    "S02": {"student_id": "S02", "name": "乙", "junior_school_id": "M01", "score": 710, "tie_seq": 1},
    "S03": {"student_id": "S03", "name": "丙", "junior_school_id": "M02", "score": 700, "tie_seq": 2},
    "S04": {"student_id": "S04", "name": "丁", "junior_school_id": "M02", "score": 655, "tie_seq": 5},
    "S05": {"student_id": "S05", "name": "戊", "junior_school_id": "M03", "score": 480, "tie_seq": 9},
    "S06": {"student_id": "S06", "name": "己", "junior_school_id": "M01", "score": 715, "tie_seq": 3},
}

# plan_id -> 计划元数据；demo=True 的 P-LARGE 只用于分页演示，不进统计。
PLANS = {
    "P-D1": {"plan_id": "P-D1", "school_id": "H02", "batch": 1, "category": "self_recruit",
             "quota": 1, "control_line": 600, "remaining": 1},
    "P-C2": {"plan_id": "P-C2", "school_id": "H01", "batch": 2, "category": "quota",
             "quota": 1, "control_line": 492, "remaining": 0},
    "P-A3": {"plan_id": "P-A3", "school_id": "H01", "batch": 3, "category": "unified",
             "quota": 2, "control_line": 492, "remaining": 0},
    "P-B3": {"plan_id": "P-B3", "school_id": "H02", "batch": 3, "category": "unified",
             "quota": 1, "control_line": 680, "remaining": 0},
    "P-G3": {"plan_id": "P-G3", "school_id": "H03", "batch": 3, "category": "unified",
             "quota": 1, "control_line": 700, "remaining": 1},
    "P-E4": {"plan_id": "P-E4", "school_id": "H03", "batch": 4, "category": "unified",
             "quota": 2, "control_line": 492, "remaining": 2},
    "P-LARGE": {"plan_id": "P-LARGE", "school_id": "H03", "batch": 3, "category": "unified",
                "quota": 120, "control_line": 492, "remaining": 0, "demo": True},
}

# run_id -> 录取结果；字段与 admit_result 一致（用于 mock 查询/导出）。
RESULTS = {
    RUN_BEFORE: [
        {"batch": 2, "plan_id": "P-C2", "student_id": "S03", "score": 700, "tie_seq": 2,
         "volunteer_no": 1, "admit_order": 1},
        {"batch": 3, "plan_id": "P-A3", "student_id": "S01", "score": 690, "tie_seq": 1,
         "volunteer_no": 1, "admit_order": 1},
        {"batch": 3, "plan_id": "P-A3", "student_id": "S02", "score": 710, "tie_seq": 1,
         "volunteer_no": 2, "admit_order": 2},
        {"batch": 3, "plan_id": "P-B3", "student_id": "S06", "score": 715, "tie_seq": 3,
         "volunteer_no": 1, "admit_order": 1},
    ],
    RUN_AFTER: [
        {"batch": 2, "plan_id": "P-C2", "student_id": "S03", "score": 700, "tie_seq": 2,
         "volunteer_no": 1, "admit_order": 1},
        {"batch": 3, "plan_id": "P-A3", "student_id": "S02", "score": 710, "tie_seq": 1,
         "volunteer_no": 2, "admit_order": 1},
        {"batch": 3, "plan_id": "P-A3", "student_id": "S04", "score": 655, "tie_seq": 5,
         "volunteer_no": 1, "admit_order": 2},
        {"batch": 3, "plan_id": "P-B3", "student_id": "S06", "score": 715, "tie_seq": 3,
         "volunteer_no": 1, "admit_order": 1},
    ],
}

# 志愿：student_id -> run_id -> [(batch, seq, plan_id, status, reason_code)]
VOLUNTEERS = {
    "S01": {
        RUN_BEFORE: [
            (3, 1, "P-A3", "admitted", None),
            (3, 2, "P-B3", "skipped", "R02"),
            (4, 1, "P-E4", "skipped", "R04"),
        ],
        RUN_AFTER: [
            (3, 1, "P-B3", "skipped", "R02"),
            (3, 2, "P-A3", "skipped", "R02"),
            (4, 1, "P-E4", "skipped", "R04"),
        ],
    },
    "S02": {
        RUN_BEFORE: [(3, 1, "P-B3", "skipped", "R02"), (3, 2, "P-A3", "admitted", None)],
        RUN_AFTER: [(3, 1, "P-B3", "skipped", "R02"), (3, 2, "P-A3", "admitted", None)],
    },
    "S03": {
        RUN_BEFORE: [(2, 1, "P-C2", "admitted", None), (3, 1, "P-A3", "skipped", "R04")],
        RUN_AFTER: [(2, 1, "P-C2", "admitted", None), (3, 1, "P-A3", "skipped", "R04")],
    },
    "S04": {
        RUN_BEFORE: [(3, 1, "P-B3", "skipped", "R02"), (3, 2, "P-G3", "skipped", "R01")],
        RUN_AFTER: [(3, 1, "P-A3", "admitted", None), (3, 2, "P-B3", "skipped", "R02")],
    },
    "S05": {
        RUN_BEFORE: [
            (1, 1, "P-D1", "skipped", "R03"),
            (3, 1, "P-A3", "skipped", "R01"),
            (3, 2, "P-B3", "skipped", "R01"),
            (4, 1, "P-E4", "skipped", "R01"),
        ],
        RUN_AFTER: [
            (1, 1, "P-D1", "skipped", "R03"),
            (3, 1, "P-A3", "skipped", "R01"),
            (3, 2, "P-B3", "skipped", "R01"),
            (4, 1, "P-E4", "skipped", "R01"),
        ],
    },
    "S06": {
        RUN_BEFORE: [(3, 1, "P-B3", "admitted", None)],
        RUN_AFTER: [(3, 1, "P-B3", "admitted", None)],
    },
}

RULES_LINES = {"control_line": 492, "gradient_first": 712, "gradient_delta": 40}
BALANCES = [
    {"batch": 1, "quota": 1, "admitted": 0, "remaining": 1},
    {"batch": 2, "quota": 1, "admitted": 1, "remaining": 0},
    {"batch": 3, "quota": 4, "admitted": 3, "remaining": 1},
    {"batch": 4, "quota": 2, "admitted": 0, "remaining": 2},
]


def _large_items() -> list[dict]:
    """P-LARGE：120 条，用来验证分页不会一次渲染整表。"""
    return [
        {"batch": 3, "plan_id": "P-LARGE", "student_id": f"S{100 + i:03d}",
         "score": 700 - i, "tie_seq": (i % 5) + 1,
         "volunteer_no": (i % 6) + 1, "admit_order": i}
        for i in range(1, 121)
    ]


def _results_for(plan_id: str, run_id: str) -> list[dict]:
    if plan_id == "P-LARGE":
        return sorted(_large_items(), key=lambda r: r["admit_order"])
    rows = [r for r in RESULTS.get(run_id, RESULTS[RUN_BEFORE]) if r["plan_id"] == plan_id]
    return sorted(rows, key=lambda r: r["admit_order"])


def _school_of(plan_id: str) -> dict | None:
    p = PLANS.get(plan_id)
    return SCHOOLS.get(p["school_id"]) if p else None


def _category_text(category: str | None) -> str:
    return {"self_recruit": "自主招生", "quota": "名额分配", "unified": "统招"}.get(
        category or "", category or "")


def _aggregate(items: list[dict]) -> dict:
    plan_count = len(items)
    quota_total = sum(i["quota_total"] for i in items)
    admitted = sum(i["admitted_count"] for i in items)
    remaining = sum(i["remaining"] for i in items)
    unfilled_plans = sum(1 for i in items if i["remaining"] > 0)
    mins = [i["min_score"] for i in items if i["min_score"] is not None]
    maxs = [i["max_score"] for i in items if i["max_score"] is not None]
    rate = round(admitted / quota_total, 4) if quota_total else 0.0
    return {
        "plan_count": plan_count,
        "quota_total": quota_total,
        "admitted_count": admitted,
        "completion_rate": rate,
        "completion_rate_text": f"{rate * 100:.2f}%",
        "unfilled_quota": max(quota_total - admitted, 0),
        "remaining_quota": remaining,
        "unfilled_plans": unfilled_plans,
        "min_score": min(mins) if mins else None,
        "max_score": max(maxs) if maxs else None,
    }


def _plan_item(plan_id: str, run_id: str) -> dict:
    p = PLANS[plan_id]
    rows = _results_for(plan_id, run_id)
    scores = [r["score"] for r in rows]
    admitted = len(rows)
    last = rows[-1] if rows else None
    return {
        "plan_id": plan_id,
        "exists": True,
        "school": _school_of(plan_id)["name"] if _school_of(plan_id) else None,
        "batch": p["batch"],
        "category": p["category"],
        "control_line": p["control_line"],
        "quota": p["quota"],
        "carry_in": 0,
        "quota_total": p["quota"],
        "admitted_count": admitted,
        "remaining": p["remaining"],
        "min_score": min(scores) if scores else None,
        "max_score": max(scores) if scores else None,
        "last_admitted": {
            "student_id": last["student_id"], "score": last["score"],
            "tie_seq": last["tie_seq"], "volunteer_no": last["volunteer_no"],
            "admit_order": last["admit_order"],
        } if last else None,
    }


def _plan_items(batch: int | None = None, school_id: str | None = None,
                run_id: str = RUN_BEFORE) -> list[dict]:
    items = []
    for pid, p in PLANS.items():
        if p.get("demo"):
            continue
        if batch is not None and p["batch"] != batch:
            continue
        if school_id is not None and p["school_id"] != school_id:
            continue
        items.append(_plan_item(pid, run_id))
    return sorted(items, key=lambda i: (i["batch"], i["plan_id"]))


def create_run(year: int, scale: str) -> dict:
    """mock 下固定返回调整前的 run_id，保证页面刷新后仍能演示。"""
    return {"run_id": RUN_BEFORE}


_LAST_PROGRESS: dict[str, dict] = {}


def execute(run_id: str, batches: list[int]) -> dict:
    progress = {
        "stage": "done",
        "done": len(batches),
        "total": len(batches),
        "balances": [b for b in BALANCES if b["batch"] in batches],
    }
    _LAST_PROGRESS[run_id] = progress
    return {"run_id": run_id, "progress": progress}


def progress(run_id: str) -> dict:
    return _LAST_PROGRESS.get(run_id, {
        "stage": "done", "done": len(BALANCES), "total": len(BALANCES),
        "balances": BALANCES,
    })


def _empty_student(run_id: str, student_id: str) -> dict:
    return {
        "run_id": run_id, "student_id": student_id, "exists": False,
        "name": None, "junior_school_id": None, "junior_school": None,
        "score": None, "tie_seq": None, "admitted": False,
        "batch": None, "plan_id": None, "school": None,
        "volunteer_no": None, "admit_order": None,
        "reason_code": None, "reason_text": None, "volunteers": [],
    }


def student_result(student_id: str, run_id: str) -> dict:
    base = STUDENTS.get(student_id)
    if base is None:
        return _empty_student(run_id, student_id)

    results = RESULTS.get(run_id, RESULTS[RUN_BEFORE])
    res = next((r for r in results if r["student_id"] == student_id), None)
    vols = VOLUNTEERS.get(student_id, {}).get(run_id, [])
    volunteers = []
    for batch, seq, plan_id, status, reason in vols:
        volunteers.append({
            "batch": batch, "seq": seq, "plan_id": plan_id,
            "status": status, "reason_code": reason,
            "reason_text": _reason_text(reason),
        })

    top_reason = None
    if res is None:
        for v in reversed(volunteers):
            if v["status"] == "skipped" and v["reason_code"]:
                top_reason = v["reason_code"]
                break

    school = _school_of(res["plan_id"]) if res else None
    return {
        "run_id": run_id,
        "student_id": student_id,
        "exists": True,
        "name": base["name"],
        "junior_school_id": base["junior_school_id"],
        "junior_school": JUNIOR_SCHOOLS.get(base["junior_school_id"]),
        "score": base["score"],
        "tie_seq": base["tie_seq"],
        "admitted": res is not None,
        "batch": res["batch"] if res else None,
        "plan_id": res["plan_id"] if res else None,
        "school": school["name"] if school else None,
        "volunteer_no": res["volunteer_no"] if res else None,
        "admit_order": res["admit_order"] if res else None,
        "reason_code": top_reason,
        "reason_text": _reason_text(top_reason),
        "volunteers": volunteers,
    }


def _empty_plan(plan_id: str, page: int, size: int) -> dict:
    return {
        "plan_id": plan_id, "exists": False, "school": None, "batch": None,
        "category": None, "control_line": None, "quota": None, "carry_in": 0,
        "quota_total": None, "admitted_count": 0, "remaining": None,
        "min_score": None, "max_score": None, "last_admitted": None,
        "items": [], "page": page, "size": size, "total": 0, "total_pages": 1,
    }


def plan_admissions(plan_id: str, run_id: str, page: int, size: int) -> dict:
    if plan_id not in PLANS:
        return _empty_plan(plan_id, page, size)
    page = max(int(page or 1), 1)
    size = min(max(int(size or 100), 1), 500)
    item = _plan_item(plan_id, run_id)
    rows = _results_for(plan_id, run_id)
    start = (page - 1) * size
    item.update({
        "items": [
            {"admit_order": r["admit_order"], "student_id": r["student_id"],
             "score": r["score"], "tie_seq": r["tie_seq"], "volunteer_no": r["volunteer_no"]}
            for r in rows[start:start + size]
        ],
        "page": page,
        "size": size,
        "total": len(rows),
        "total_pages": max(math.ceil(len(rows) / size), 1),
    })
    return item


def batch_stats(batch: int, run_id: str) -> dict:
    items = _plan_items(batch=batch, run_id=run_id)
    volunteered = {sid for sid, by_run in VOLUNTEERS.items()
                   if any(v[0] == batch for v in by_run.get(run_id, []))}
    admitted = {r["student_id"] for r in RESULTS.get(run_id, RESULTS[RUN_BEFORE])
                if r["batch"] == batch}
    out = {"run_id": run_id, "batch": batch}
    out.update(_aggregate(items))
    out["volunteered_students"] = len(volunteered)
    out["unadmitted_students"] = len(volunteered - admitted)
    out["plans"] = [
        {"plan_id": i["plan_id"], "school": i["school"], "category": i["category"],
         "quota_total": i["quota_total"], "admitted_count": i["admitted_count"],
         "remaining": i["remaining"], "min_score": i["min_score"]}
        for i in items
    ]
    return out


def school_stats(school_id: str, run_id: str) -> dict:
    school = SCHOOLS.get(school_id)
    items = _plan_items(school_id=school_id, run_id=run_id) if school else []
    overall = _aggregate(items)
    by_batch = []
    for batch in sorted({i["batch"] for i in items}):
        agg = _aggregate([i for i in items if i["batch"] == batch])
        by_batch.append({"batch": batch, **agg})
    by_category = []
    for category in sorted({i["category"] for i in items}):
        agg = _aggregate([i for i in items if i["category"] == category])
        by_category.append({"category": category, **_category_fields(agg)})
    return {
        "run_id": run_id,
        "school_id": school_id,
        "school": school["name"] if school else None,
        "exists": school is not None,
        "overall": overall,
        "by_batch": by_batch,
        "by_category": by_category,
        "plans": [
            {"plan_id": i["plan_id"], "batch": i["batch"], "category": i["category"],
             "quota_total": i["quota_total"], "admitted_count": i["admitted_count"],
             "remaining": i["remaining"], "min_score": i["min_score"],
             "last_admitted": i["last_admitted"]}
            for i in items
        ],
    }


def _category_fields(agg: dict) -> dict:
    return dict(agg)


def distribution(batch: int, run_id: str, bucket_size: int = 10) -> dict:
    scores = [r["score"] for r in RESULTS.get(run_id, RESULTS[RUN_BEFORE])
              if r["batch"] == batch]
    bucket_size = max(int(bucket_size or 10), 1)
    buckets: dict[int, int] = {}
    for s in scores:
        low = (int(s) // bucket_size) * bucket_size
        buckets[low] = buckets.get(low, 0) + 1
    return {
        "run_id": run_id, "batch": batch, "bucket_size": bucket_size,
        "buckets": [
            {"label": f"{low}-{low + bucket_size - 1}", "low": low,
             "high": low + bucket_size - 1, "count": buckets[low]}
            for low in sorted(buckets, reverse=True)
        ],
        "total": len(scores),
        "min_score": min(scores) if scores else None,
        "max_score": max(scores) if scores else None,
        "lines": RULES_LINES,
    }


def reasons() -> list[dict]:
    return REASONS


def _stat_row(dim: str, name: str, agg: dict) -> list:
    return [
        dim, name, agg["plan_count"], agg["quota_total"], agg["admitted_count"],
        agg["completion_rate_text"], agg["unfilled_quota"], agg["unfilled_plans"],
        "无" if agg["min_score"] is None else agg["min_score"],
        "无" if agg["max_score"] is None else agg["max_score"],
    ]


def stats_csv(run_id: str) -> str:
    """与 4 号统计汇总 CSV 同列；维度含全校/分批/按校。"""
    header = ["维度", "对象", "计划数", "有效计划数", "录取数", "完成率",
              "未完成名额", "未完成计划数", "最低录取分", "最高录取分"]
    rows = [_stat_row("全校", "全部批次", _aggregate(_plan_items(run_id=run_id)))]
    for batch in (1, 2, 3, 4):
        agg = _aggregate(_plan_items(batch=batch, run_id=run_id))
        rows.append(_stat_row("分批", f"第 {batch} 批", agg))
    for school_id, school in SCHOOLS.items():
        agg = _aggregate(_plan_items(school_id=school_id, run_id=run_id))
        rows.append(_stat_row("按校", f"{school['name']}（{school_id}）", agg))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return "﻿" + buf.getvalue()


def admissions_csv(run_id: str) -> str:
    """与 4 号导出同列：中文表头、UTF-8 BOM、一行一条录取记录。"""
    header = ["运行编号", "考生编号", "姓名", "初中", "批次", "批次类别",
              "计划编号", "高中", "录取总分", "同分序号", "志愿序号", "录取顺序"]
    rows = sorted(RESULTS.get(run_id, RESULTS[RUN_BEFORE]),
                  key=lambda r: (r["batch"], r["plan_id"], r["admit_order"]))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for r in rows:
        stu = STUDENTS.get(r["student_id"], {})
        plan = PLANS.get(r["plan_id"], {})
        school = _school_of(r["plan_id"]) or {}
        writer.writerow([
            run_id, r["student_id"], stu.get("name"),
            JUNIOR_SCHOOLS.get(stu.get("junior_school_id")),
            r["batch"], _category_text(plan.get("category")),
            r["plan_id"], school.get("name"), r["score"], r["tie_seq"],
            r["volunteer_no"], r["admit_order"],
        ])
    return "﻿" + buf.getvalue()
