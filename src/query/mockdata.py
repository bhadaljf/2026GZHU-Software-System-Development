"""首版联调用的 mock 数据（4 号：黎俊彤）。

用途：2 号的建表脚本、3 号的引擎还没交付时，6 号页面要能先跑起来。
数据刻意与 docs/08_协作规范与样例.md 第 6 节同形：
P-A3 计划 quota=2、最低分 690（S01）、末位考生 S02（710，志愿序号 2），
另有无人录取的计划 P-G3（最低分/末位考生为 None，页面显示“无”）。

注意：这是假数据，只用于联调与自检，不得用于对账或写进报告。
"""

from __future__ import annotations

# 初中
JUNIOR_SCHOOLS = {
    "M01": "M 一中",
    "M02": "M 二中",
    "M03": "M 三中",
}

# 高中
SCHOOLS = [
    {"school_id": "H01", "name": "A 校", "type": "public", "recruit_batch": 3},
    {"school_id": "H02", "name": "B 校", "type": "public", "recruit_batch": 3},
    {"school_id": "H03", "name": "C 校", "type": "public", "recruit_batch": 4},
]

# 考生
STUDENTS = [
    {"student_id": "S01", "name": "甲", "junior_school_id": "M01", "score": 690, "tie_seq": 1},
    {"student_id": "S02", "name": "乙", "junior_school_id": "M01", "score": 710, "tie_seq": 1},
    {"student_id": "S03", "name": "丙", "junior_school_id": "M02", "score": 700, "tie_seq": 2},
    {"student_id": "S04", "name": "丁", "junior_school_id": "M02", "score": 655, "tie_seq": 5},
    {"student_id": "S05", "name": "戊", "junior_school_id": "M03", "score": 480, "tie_seq": 9},
    {"student_id": "S06", "name": "己", "junior_school_id": "M01", "score": 715, "tie_seq": 3},
]

# 招生计划（quota 已按 R5 切分；remaining 为当前剩余名额）
PLANS = [
    {"plan_id": "P-D1", "year": 2026, "high_school_id": "H02", "batch": 1,
     "category": "self_recruit", "quota": 1, "control_line": 600, "remaining": 1},
    {"plan_id": "P-C2", "year": 2026, "high_school_id": "H01", "batch": 2,
     "category": "quota", "quota": 1, "control_line": 492, "remaining": 0},
    {"plan_id": "P-A3", "year": 2026, "high_school_id": "H01", "batch": 3,
     "category": "unified", "quota": 2, "control_line": 492, "remaining": 0},
    {"plan_id": "P-B3", "year": 2026, "high_school_id": "H02", "batch": 3,
     "category": "unified", "quota": 1, "control_line": 680, "remaining": 0},
    {"plan_id": "P-G3", "year": 2026, "high_school_id": "H03", "batch": 3,
     "category": "unified", "quota": 1, "control_line": 700, "remaining": 1},
    {"plan_id": "P-E4", "year": 2026, "high_school_id": "H03", "batch": 4,
     "category": "unified", "quota": 2, "control_line": 492, "remaining": 2},
]

# 志愿（year, student_id, batch, seq, plan_id）
VOLUNTEERS = [
    {"year": 2026, "student_id": "S01", "batch": 3, "seq": 1, "plan_id": "P-A3"},
    {"year": 2026, "student_id": "S01", "batch": 3, "seq": 2, "plan_id": "P-B3"},
    {"year": 2026, "student_id": "S01", "batch": 4, "seq": 1, "plan_id": "P-E4"},
    {"year": 2026, "student_id": "S02", "batch": 3, "seq": 1, "plan_id": "P-B3"},
    {"year": 2026, "student_id": "S02", "batch": 3, "seq": 2, "plan_id": "P-A3"},
    {"year": 2026, "student_id": "S03", "batch": 2, "seq": 1, "plan_id": "P-C2"},
    {"year": 2026, "student_id": "S03", "batch": 3, "seq": 1, "plan_id": "P-A3"},
    {"year": 2026, "student_id": "S04", "batch": 3, "seq": 1, "plan_id": "P-B3"},
    {"year": 2026, "student_id": "S04", "batch": 3, "seq": 2, "plan_id": "P-G3"},
    {"year": 2026, "student_id": "S05", "batch": 1, "seq": 1, "plan_id": "P-D1"},
    {"year": 2026, "student_id": "S05", "batch": 3, "seq": 1, "plan_id": "P-A3"},
    {"year": 2026, "student_id": "S05", "batch": 3, "seq": 2, "plan_id": "P-B3"},
    {"year": 2026, "student_id": "S05", "batch": 4, "seq": 1, "plan_id": "P-E4"},
    {"year": 2026, "student_id": "S06", "batch": 3, "seq": 1, "plan_id": "P-B3"},
]

# 录取结果（字段与契约 admit_result 一致）
RESULTS = [
    {"result_id": "RUN-MOCK-2-P-C2-1", "run_id": "RUN-MOCK", "batch": 2, "plan_id": "P-C2",
     "student_id": "S03", "score": 700, "tie_seq": 2, "volunteer_no": 1, "admit_order": 1},
    {"result_id": "RUN-MOCK-3-P-A3-1", "run_id": "RUN-MOCK", "batch": 3, "plan_id": "P-A3",
     "student_id": "S01", "score": 690, "tie_seq": 1, "volunteer_no": 1, "admit_order": 1},
    {"result_id": "RUN-MOCK-3-P-A3-2", "run_id": "RUN-MOCK", "batch": 3, "plan_id": "P-A3",
     "student_id": "S02", "score": 710, "tie_seq": 1, "volunteer_no": 2, "admit_order": 2},
    {"result_id": "RUN-MOCK-3-P-B3-1", "run_id": "RUN-MOCK", "batch": 3, "plan_id": "P-B3",
     "student_id": "S06", "score": 715, "tie_seq": 3, "volunteer_no": 1, "admit_order": 1},
]

# 投档日志（字段与契约 admit_log 一致；band：1 最高，0 表示低于 L）
LOGS = [
    # S01：三批先录 A 校；同批第二志愿 B 校已满；四批前批已录取
    {"log_id": "L01", "run_id": "RUN-MOCK", "batch": 3, "band": 2, "volunteer_no": 1,
     "plan_id": "P-A3", "student_id": "S01", "action": "admit", "reason_code": None,
     "balance_before": 2, "balance_after": 1, "note": "名额充足"},
    {"log_id": "L02", "run_id": "RUN-MOCK", "batch": 3, "band": 2, "volunteer_no": 2,
     "plan_id": "P-B3", "student_id": "S01", "action": "skip", "reason_code": "R02",
     "balance_before": 0, "balance_after": 0, "note": "名额已满"},
    {"log_id": "L03", "run_id": "RUN-MOCK", "batch": 4, "band": 2, "volunteer_no": 1,
     "plan_id": "P-E4", "student_id": "S01", "action": "skip", "reason_code": "R04",
     "balance_before": 2, "balance_after": 2, "note": "前批已录取"},
    # S02：第一志愿 B 校已满，第二志愿 A 校录取
    {"log_id": "L04", "run_id": "RUN-MOCK", "batch": 3, "band": 1, "volunteer_no": 1,
     "plan_id": "P-B3", "student_id": "S02", "action": "skip", "reason_code": "R02",
     "balance_before": 0, "balance_after": 0, "note": "名额已满"},
    {"log_id": "L05", "run_id": "RUN-MOCK", "batch": 3, "band": 1, "volunteer_no": 2,
     "plan_id": "P-A3", "student_id": "S02", "action": "admit", "reason_code": None,
     "balance_before": 1, "balance_after": 0, "note": "同梯度志愿优先"},
    # S03：二批已录，三批记前批已录取
    {"log_id": "L06", "run_id": "RUN-MOCK", "batch": 2, "band": 2, "volunteer_no": 1,
     "plan_id": "P-C2", "student_id": "S03", "action": "admit", "reason_code": None,
     "balance_before": 1, "balance_after": 0, "note": "名额到校"},
    {"log_id": "L07", "run_id": "RUN-MOCK", "batch": 3, "band": 2, "volunteer_no": 1,
     "plan_id": "P-A3", "student_id": "S03", "action": "skip", "reason_code": "R04",
     "balance_before": 1, "balance_after": 1, "note": "前批已录取"},
    # S04：B 校已满、G 校未达控制线 -> 全部批次未录取
    {"log_id": "L08", "run_id": "RUN-MOCK", "batch": 3, "band": 2, "volunteer_no": 1,
     "plan_id": "P-B3", "student_id": "S04", "action": "skip", "reason_code": "R02",
     "balance_before": 0, "balance_after": 0, "note": "名额已满"},
    {"log_id": "L09", "run_id": "RUN-MOCK", "batch": 3, "band": 2, "volunteer_no": 2,
     "plan_id": "P-G3", "student_id": "S04", "action": "skip", "reason_code": "R01",
     "balance_before": 1, "balance_after": 1, "note": "655 < 控制线 700"},
    # S05：资格不符 + 低于控制线
    {"log_id": "L10", "run_id": "RUN-MOCK", "batch": 1, "band": 1, "volunteer_no": 1,
     "plan_id": "P-D1", "student_id": "S05", "action": "skip", "reason_code": "R03",
     "balance_before": 1, "balance_after": 1, "note": "不在自主招生资格名单"},
    {"log_id": "L11", "run_id": "RUN-MOCK", "batch": 3, "band": 0, "volunteer_no": 1,
     "plan_id": "P-A3", "student_id": "S05", "action": "skip", "reason_code": "R01",
     "balance_before": 1, "balance_after": 1, "note": "480 < 492"},
    {"log_id": "L12", "run_id": "RUN-MOCK", "batch": 3, "band": 0, "volunteer_no": 2,
     "plan_id": "P-B3", "student_id": "S05", "action": "skip", "reason_code": "R01",
     "balance_before": 0, "balance_after": 0, "note": "480 < 680"},
    {"log_id": "L13", "run_id": "RUN-MOCK", "batch": 4, "band": 0, "volunteer_no": 1,
     "plan_id": "P-E4", "student_id": "S05", "action": "skip", "reason_code": "R01",
     "balance_before": 2, "balance_after": 2, "note": "480 < 492"},
    # S06：B 校录取
    {"log_id": "L14", "run_id": "RUN-MOCK", "batch": 3, "band": 1, "volunteer_no": 1,
     "plan_id": "P-B3", "student_id": "S06", "action": "admit", "reason_code": None,
     "balance_before": 1, "balance_after": 0, "note": "名额充足"},
]

# 结转流水（本例无结转，保留空表以便字段对齐）
CARRY_LOGS: list[dict] = []

# 运行快照（供 report 的 run 元信息）
RUN_META = {
    "run_id": "RUN-MOCK",
    "year": 2026,
    "data_version": "mock-v1",
    "operator": "4",
    "created_at": "2026-11-21T10:00:00+08:00",
}

# 规则参数（与 config/rules.toml 一致，默认值仅用于 mock 展示）
RULES = {
    "year": 2026,
    "control_line": 492,
    "gradient": {"first_line": 712, "delta": 40},
}


def student(student_id: str) -> dict | None:
    """按编号取考生。"""
    for s in STUDENTS:
        if s["student_id"] == student_id:
            return s
    return None


def junior_name(junior_school_id: str | None) -> str | None:
    """初中编号 -> 名称。"""
    return JUNIOR_SCHOOLS.get(junior_school_id or "")


def plan(plan_id: str) -> dict | None:
    """按编号取计划。"""
    for p in PLANS:
        if p["plan_id"] == plan_id:
            return p
    return None


def school_of_plan(plan_id: str) -> dict | None:
    """计划 -> 高中。"""
    p = plan(plan_id)
    if p is None:
        return None
    for s in SCHOOLS:
        if s["school_id"] == p["high_school_id"]:
            return s
    return None
