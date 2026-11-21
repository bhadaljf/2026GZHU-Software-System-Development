"""CSV 导出（4 号：黎俊彤）。

职责：把结果与统计导成文件（R35：CSV 必须有字段头，且附口径说明）。
入参：run_id；可选 out_path、conn、mock
出参：生成文件的绝对路径（str）

约定：
- 编码 utf-8-sig，Excel 直接双击不乱码；
- 空值（最低录取分、末位考生）写“无”，不写 0（R32）；
- 每次导出同时生成同名 `*_口径说明.md`，写明 run_id、列含义、空值规则。
"""

from __future__ import annotations

import csv
import datetime as _dt
import re
import sqlite3
from pathlib import Path

try:
    from src.query import EXPORT_DIR, open_cursor, use_mock
    from src.query import mockdata as _mock
    from src.report.report import build_stats_report
except ImportError:  # 以 src 为 sys.path 导入时
    from query import EXPORT_DIR, open_cursor, use_mock
    from query import mockdata as _mock
    from report.report import build_stats_report

# 录取结果 CSV 列顺序（固定，别随意改列序，6 号与 1 号的表头按这个对）
ADMISSION_COLUMNS = [
    "运行编号", "考生编号", "姓名", "初中", "批次", "批次类别",
    "计划编号", "高中", "录取总分", "同分序号", "志愿序号", "录取顺序",
]

# 统计汇总 CSV 列顺序
STAT_COLUMNS = [
    "维度", "对象", "计划数", "有效计划数", "录取数", "完成率",
    "未完成名额", "未完成计划数", "最低录取分", "最高录取分",
]

NOT_FOUND = "无"  # 空值统一写法（R32）


def export_admissions(run_id: str, out_path: str | None = None, *,
                      conn=None, mock=None, with_note: bool = True) -> str:
    """导出录取结果明细（一行 = 一条录取记录）。"""
    path = _resolve(out_path, "录取结果", run_id)
    rows = _admission_rows(run_id, conn=conn, mock=mock)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(ADMISSION_COLUMNS)
        for r in rows:
            w.writerow([r.get(c) if r.get(c) is not None else "" for c in ADMISSION_COLUMNS])

    if with_note:
        _write_note(path, run_id, len(rows), [
            "一行一条录取记录，按批次 → 计划 → 录取顺序排序。",
            "录取总分为录取时的快照（admit_result.score），与考生当前分数可能不同。",
            "同分序号越小越优先（R16）；志愿序号为该生被录的第几志愿。",
            "录取顺序 = 该计划内的 admit_order，从 1 连续编号。",
        ])
    return str(path)


def export_stats(run_id: str, out_path: str | None = None, *,
                 conn=None, mock=None, with_note: bool = True) -> str:
    """导出统计汇总（全校 / 分批 / 分类 / 按校 四个维度各一行一段）。"""
    path = _resolve(out_path, "统计汇总", run_id)
    report = build_stats_report(run_id, conn=conn, mock=mock)

    rows = [_stat_row("全校", "全部批次", report["overall"])]
    for b in report["by_batch"]:
        rows.append(_stat_row("分批", f"第 {b['batch']} 批", b))
    for c in report["by_category"]:
        rows.append(_stat_row("分类", _category_text(c["category"]), c))
    for s in report["by_school"]:
        rows.append(_stat_row("按校", f"{s['school']}（{s['school_id']}）", s))

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(STAT_COLUMNS)
        w.writerows(rows)

    if with_note:
        checked = report["conservation"]
        notes = list(report["notes"]) + [
            f"余额守恒核对：共核对 {checked['checked']} 个计划，不一致 {checked['mismatch']} 个。",
        ]
        _write_note(path, run_id, len(rows), notes)
    return str(path)


# ---------------------------------------------------------------- 内部实现

def _admission_rows(run_id: str, conn=None, mock=None) -> list[dict]:
    """取导出行；库与 mock 两条路径都返回同样的键。"""
    if use_mock(mock):
        rows = []
        for r in sorted(_mock.RESULTS, key=lambda x: (x["batch"], x["plan_id"], x["admit_order"])):
            stu = _mock.student(r["student_id"]) or {}
            plan = _mock.plan(r["plan_id"]) or {}
            school = _mock.school_of_plan(r["plan_id"]) or {}
            rows.append({
                "运行编号": run_id,
                "考生编号": r["student_id"],
                "姓名": stu.get("name"),
                "初中": _mock.junior_name(stu.get("junior_school_id")),
                "批次": r["batch"],
                "批次类别": _category_text(plan.get("category")),
                "计划编号": r["plan_id"],
                "高中": school.get("name"),
                "录取总分": r["score"],
                "同分序号": r["tie_seq"],
                "志愿序号": r["volunteer_no"],
                "录取顺序": r["admit_order"],
            })
        return rows

    sql = ("SELECT r.run_id, r.student_id, s.name AS name, m.name AS junior_school, "
           "       r.batch, p.category, r.plan_id, h.name AS school, "
           "       r.score, r.tie_seq, r.volunteer_no, r.admit_order "
           "FROM admit_result r "
           "LEFT JOIN student s ON s.student_id = r.student_id "
           "LEFT JOIN middle_school m ON m.school_id = s.junior_school_id "
           "LEFT JOIN plan p ON p.plan_id = r.plan_id "
           "LEFT JOIN high_school h ON h.school_id = p.high_school_id "
           "WHERE r.run_id = ? ORDER BY r.batch, r.plan_id, r.admit_order")
    with open_cursor(conn) as cur:
        data = cur.execute(sql, (run_id,)).fetchall()

    return [{
        "运行编号": row["run_id"],
        "考生编号": row["student_id"],
        "姓名": row["name"],
        "初中": row["junior_school"],
        "批次": row["batch"],
        "批次类别": _category_text(row["category"]),
        "计划编号": row["plan_id"],
        "高中": row["school"],
        "录取总分": row["score"],
        "同分序号": row["tie_seq"],
        "志愿序号": row["volunteer_no"],
        "录取顺序": row["admit_order"],
    } for row in data]


def _stat_row(dim: str, name: str, agg: dict) -> list:
    """一行统计；最低录取分没人录取时写“无”。"""
    min_score = agg.get("min_score")
    max_score = agg.get("max_score")
    return [
        dim,
        name,
        agg.get("plan_count", 0),
        agg.get("quota_total", 0),
        agg.get("admitted_count", 0),
        agg.get("completion_rate_text") or f"{(agg.get('completion_rate') or 0) * 100:.2f}%",
        agg.get("unfilled_quota", 0),
        agg.get("unfilled_plans", 0),
        NOT_FOUND if min_score is None else min_score,
        NOT_FOUND if max_score is None else max_score,
    ]


def _category_text(category: str | None) -> str:
    """计划类别转中文。"""
    return {"self_recruit": "自主招生", "quota": "名额分配", "unified": "统招"}.get(
        category or "", category or "")


def _resolve(out_path: str | None, prefix: str, run_id: str) -> Path:
    """默认落到 export/ 下，文件名带 run_id；显式路径直接用。"""
    if out_path:
        return Path(out_path)
    safe = re.sub(r"[^0-9A-Za-z_\-]", "_", run_id or "RUN")
    return EXPORT_DIR / f"{prefix}_{safe}.csv"


def _write_note(csv_path: Path, run_id: str, row_count: int, notes: list[str]) -> Path:
    """同目录写一份口径说明 md（R35 要求导出不能“口径不明”）。"""
    note = csv_path.with_name(csv_path.stem + "_口径说明.md")
    lines = [
        f"# {csv_path.name} 口径说明",
        "",
        f"- 运行编号：`{run_id}`",
        f"- 生成时间：{_dt.datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- 数据行数：{row_count}（不含表头）",
        f"- 编码：UTF-8 with BOM（Excel 可直接打开）",
        "",
        "## 口径",
        "",
    ]
    lines += [f"{i + 1}. {n}" for i, n in enumerate(notes)]
    lines += ["", "> 空值一律写“无”，不得写 0（R32）。", ""]
    note.write_text("\n".join(lines), encoding="utf-8")
    return note
