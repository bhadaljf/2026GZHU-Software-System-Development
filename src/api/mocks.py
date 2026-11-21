"""接口假数据（6 号，仅开发/演示用）。

用途：2/3/4 号模块未就绪时，让 `interface/` 五个区块可以独立点通（T-06）。
开关：环境变量 ``API_MOCK=1``；默认关闭，真实模式不会回退到本模块。
字段形状：docs/08_协作规范与样例.md 第 6 节、docs/09_接口清单.md 第 3 节。

真实模块就绪后本文件可保留为回归样例，但不得在真实运行/演示成片中启用。
"""

from __future__ import annotations

import csv
import io
import os

MOCK = os.getenv("API_MOCK", "0") == "1"

# 案例对比页固定使用这两个 run_id：调整前 / 调整后。
RUN_BEFORE = "RUN20261121-01"
RUN_AFTER = "RUN20261121-02"

REASONS = [
    {"code": "R01", "text": "未达计划控制线或最低控制线 L"},
    {"code": "R02", "text": "计划名额已满"},
    {"code": "R03", "text": "不在自主招生资格名单或排名不达"},
    {"code": "R04", "text": "前批已录取"},
    {"code": "R05", "text": "非所属初中名额"},
    {"code": "R06", "text": "志愿或计划无效"},
    {"code": "R07", "text": "未填报该计划"},
]

BALANCES = [
    {"batch": 1, "quota": 40, "admitted": 36, "remaining": 4},
    {"batch": 2, "quota": 200, "admitted": 180, "remaining": 20},
    {"batch": 3, "quota": 160, "admitted": 150, "remaining": 10},
    {"batch": 4, "quota": 20, "admitted": 0, "remaining": 20},
]

# 考生基础信息；S01—S04 与录取样例、案例对比保持一致。
_STUDENTS = {
    "S01": {"student_id": "S01", "score": 690, "tie_seq": 1},
    "S02": {"student_id": "S02", "score": 710, "tie_seq": 1},
    "S03": {"student_id": "S03", "score": 680, "tie_seq": 2},
    "S04": {"student_id": "S04", "score": 700, "tie_seq": 1},
    "S09": {"student_id": "S09", "score": 688, "tie_seq": 1},
}

_VOLUNTEERS = {
    "S01": [
        {"batch": 3, "seq": 1, "plan_id": "P-A3", "status": "admitted", "reason_code": None},
        {"batch": 3, "seq": 2, "plan_id": "P-C3", "status": "skipped", "reason_code": "R04"},
    ],
    # 调整志愿后：第一志愿改报 B 校，落选；第二志愿 A 校已满。
    "S01_after": [
        {"batch": 3, "seq": 1, "plan_id": "P-B3", "status": "skipped", "reason_code": "R02"},
        {"batch": 3, "seq": 2, "plan_id": "P-A3", "status": "skipped", "reason_code": "R02"},
    ],
    "S02": [
        {"batch": 3, "seq": 1, "plan_id": "P-B3", "status": "skipped", "reason_code": "R02"},
        {"batch": 3, "seq": 2, "plan_id": "P-A3", "status": "admitted", "reason_code": None},
    ],
    "S03": [
        {"batch": 3, "seq": 1, "plan_id": "P-B3", "status": "skipped", "reason_code": "R02"},
        {"batch": 3, "seq": 2, "plan_id": "P-A3", "status": "skipped", "reason_code": "R02"},
    ],
    "S04": [
        {"batch": 3, "seq": 1, "plan_id": "P-A3", "status": "admitted", "reason_code": None},
    ],
    # 调整前 S04 未填报 A 校，只有 B 校志愿且落选。
    "S04_before": [
        {"batch": 3, "seq": 1, "plan_id": "P-B3", "status": "skipped", "reason_code": "R02"},
    ],
    "S09": [
        {"batch": 3, "seq": 1, "plan_id": "P-B3", "status": "admitted", "reason_code": None},
    ],
}

# 计划名单：P-A3 与 docs/08 第 6 节样例一致；调整后的 run 里 S01 被 S04 取代。
_PLAN_ITEMS = {
    "P-A3": {
        RUN_BEFORE: [
            {"admit_order": 1, "student_id": "S01", "score": 690, "tie_seq": 1, "volunteer_no": 1},
            {"admit_order": 2, "student_id": "S02", "score": 710, "tie_seq": 1, "volunteer_no": 2},
        ],
        RUN_AFTER: [
            {"admit_order": 1, "student_id": "S02", "score": 710, "tie_seq": 1, "volunteer_no": 2},
            {"admit_order": 2, "student_id": "S04", "score": 700, "tie_seq": 1, "volunteer_no": 1},
        ],
    },
    "P-B3": {
        RUN_BEFORE: [
            {"admit_order": 1, "student_id": "S09", "score": 688, "tie_seq": 1, "volunteer_no": 1},
        ],
        RUN_AFTER: [
            {"admit_order": 1, "student_id": "S09", "score": 688, "tie_seq": 1, "volunteer_no": 1},
        ],
    },
}


def _large_items() -> list[dict]:
    """P-LARGE：120 条，用来验证分页不会一次渲染整表。"""
    return [
        {
            "admit_order": i,
            "student_id": f"S{100 + i:03d}",
            "score": 700 - i,
            "tie_seq": (i % 5) + 1,
            "volunteer_no": (i % 6) + 1,
        }
        for i in range(1, 121)
    ]


def _items_for(pid: str, run_id: str) -> list[dict]:
    if pid == "P-LARGE":
        return _large_items()
    table = _PLAN_ITEMS.get(pid)
    if table is None:
        raise KeyError(pid)
    return table.get(run_id, table[RUN_BEFORE])


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
        "stage": "done",
        "done": len(BALANCES),
        "total": len(BALANCES),
        "balances": BALANCES,
    })


def _admitted(base: dict, run_id: str, batch: int, plan_id: str, school: str,
              volunteer_no: int, admit_order: int, volunteers: list[dict]) -> dict:
    return {
        **base,
        "run_id": run_id,
        "admitted": True,
        "batch": batch,
        "plan_id": plan_id,
        "school": school,
        "volunteer_no": volunteer_no,
        "admit_order": admit_order,
        "volunteers": volunteers,
    }


def _rejected(base: dict, run_id: str, volunteers: list[dict]) -> dict:
    return {
        **base,
        "run_id": run_id,
        "admitted": False,
        "batch": None,
        "plan_id": None,
        "school": None,
        "volunteer_no": None,
        "admit_order": None,
        "volunteers": volunteers,
    }


def student_result(student_id: str, run_id: str) -> dict:
    base = _STUDENTS.get(student_id)
    if base is None:
        raise KeyError(student_id)

    after = run_id == RUN_AFTER

    if student_id == "S01":
        if after:
            return _rejected(base, run_id, _VOLUNTEERS["S01_after"])
        return _admitted(base, run_id, 3, "P-A3", "A 校", 1, 1, _VOLUNTEERS["S01"])

    if student_id == "S02":
        # 调整前 S02 是 A 校第 2 个录取；调整后 S01 退出，S02 升为第 1 个。
        return _admitted(
            base, run_id, 3, "P-A3", "A 校", 2, 1 if after else 2, _VOLUNTEERS["S02"],
        )

    if student_id == "S04":
        if after:
            return _admitted(base, run_id, 3, "P-A3", "A 校", 1, 2, _VOLUNTEERS["S04"])
        return _rejected(base, run_id, _VOLUNTEERS["S04_before"])

    if student_id == "S09":
        return _admitted(base, run_id, 3, "P-B3", "B 校", 1, 1, _VOLUNTEERS["S09"])

    return _rejected(base, run_id, _VOLUNTEERS["S03"])


def plan_admissions(plan_id: str, run_id: str, page: int, size: int) -> dict:
    items = _items_for(plan_id, run_id)
    admitted = len(items)
    scores = [it["score"] for it in items]
    quota = admitted
    start = (page - 1) * size
    return {
        "plan_id": plan_id,
        "quota": quota,
        "admitted_count": admitted,
        "remaining": max(0, quota - admitted),
        "min_score": min(scores) if scores else None,
        "last_admitted": items[-1] if items else None,
        "items": items[start:start + size],
        "page": page,
        "size": size,
        "total": len(items),
    }


_BATCH_STATS = {
    1: {"plan_count": 40, "admitted_count": 36, "fill_rate": 0.9, "unadmitted_count": 4, "min_score": 650},
    2: {"plan_count": 200, "admitted_count": 180, "fill_rate": 0.9, "unadmitted_count": 20, "min_score": 600},
    3: {"plan_count": 160, "admitted_count": 150, "fill_rate": 0.9375, "unadmitted_count": 10, "min_score": 492},
    # 第四批故意留一个“无人录取”的口径样例：min_score 为 null，界面显示“无”。
    4: {"plan_count": 20, "admitted_count": 0, "fill_rate": 0.0, "unadmitted_count": 20, "min_score": None},
}


def batch_stats(batch: int, run_id: str) -> dict:
    return {"run_id": run_id, "batch": batch, **_BATCH_STATS[batch]}


_SCHOOL_STATS = {
    "H-A": {
        "school_id": "H-A",
        "name": "A 校",
        "plan_count": 60,
        "admitted_count": 50,
        "fill_rate": 0.8333,
        "unadmitted_count": 10,
        "min_score": 690,
        "last_admitted": {"student_id": "S02", "score": 710, "tie_seq": 1, "volunteer_no": 2},
    },
    "H-B": {
        "school_id": "H-B",
        "name": "B 校",
        "plan_count": 40,
        "admitted_count": 40,
        "fill_rate": 1.0,
        "unadmitted_count": 0,
        "min_score": 688,
        "last_admitted": {"student_id": "S09", "score": 688, "tie_seq": 1, "volunteer_no": 1},
    },
}


def school_stats(school_id: str, run_id: str) -> dict:
    data = _SCHOOL_STATS.get(school_id)
    if data is None:
        raise KeyError(school_id)
    return {"run_id": run_id, **data}


_DISTRIBUTION = {
    1: [("≥712", 0), ("672—711", 8), ("632—671", 12), ("592—631", 10), ("552—591", 6), ("492—551", 0)],
    2: [("≥712", 2), ("672—711", 30), ("632—671", 60), ("592—631", 55), ("552—591", 33), ("492—551", 0)],
    3: [("≥712", 0), ("672—711", 12), ("632—671", 48), ("592—631", 50), ("552—591", 30), ("492—551", 10)],
    4: [("≥712", 0), ("672—711", 0), ("632—671", 0), ("592—631", 0), ("552—591", 0), ("492—551", 0)],
}


def distribution(batch: int, run_id: str) -> dict:
    buckets = [{"label": label, "count": count} for label, count in _DISTRIBUTION[batch]]
    return {
        "run_id": run_id,
        "batch": batch,
        "buckets": buckets,
        "total": sum(b["count"] for b in buckets),
    }


def reasons() -> list[dict]:
    return REASONS


def admissions_csv(run_id: str) -> str:
    """返回带 BOM 的 UTF-8 CSV，Excel 直接打开不乱码。"""
    items = _items_for("P-A3", run_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "run_id", "batch", "plan_id", "student_id",
        "score", "tie_seq", "volunteer_no", "admit_order",
    ])
    for it in items:
        writer.writerow([
            run_id, 3, "P-A3", it["student_id"],
            it["score"], it["tie_seq"], it["volunteer_no"], it["admit_order"],
        ])
    return chr(0xFEFF) + buf.getvalue()
