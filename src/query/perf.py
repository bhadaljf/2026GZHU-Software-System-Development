"""性能支撑：计时、统计汇总表读取、建议索引（4 号：黎俊彤）。

对应第二阶段任务（`docs/07_分工与计划.md`「4 号 + 6 号：接口与界面联调，统计改读汇总表」、
「性能：统计读汇总表或物化视图，常用查询走覆盖索引，不在线聚合 15 万明细；记录三类查询的响应时间」）。

分工边界：
- 4 号只读库，**不建表**。本文件只提供汇总表 DDL 与索引 DDL 的**文本**，由 2 号在
  `db/schema*.sql` 与 `src/store.init_db` 里执行；
- 汇总表不存在时，`read_plan_summary()` 返回 None，统计自动回退在线聚合，行为与首版完全一致，
  所以 2 号还没建表也不会坏；
- 计时入口 `timed()` 供 `src/query/bench.py` 记录三类查询的响应时间，供 1 号报告取数。

入参：sqlite3.Cursor、run_id
出参：`read_plan_summary` -> list[dict] | None；`summary_ddl()` -> str；`index_ddl()` -> list[str]
"""

from __future__ import annotations

import contextlib
import sqlite3
import time

# 汇总表名与列（列名与 stats._plan_items 的内部行结构一一对应，读出来不用二次换算）
SUMMARY_TABLE = "plan_summary"

SUMMARY_COLUMNS = (
    "run_id", "plan_id", "batch", "category", "school_id", "school_name",
    "quota", "carry_in", "quota_total", "admitted_count", "remaining",
    "min_score", "max_score",
    "last_student_id", "last_score", "last_tie_seq", "last_volunteer_no", "last_admit_order",
)


@contextlib.contextmanager
def timed():
    """计时上下文：`with timed() as t:` 退出后 `t["ms"]` 为毫秒（保留两位）。

    用法见 `src/query/bench.py`；只做测量，不改变任何业务返回值。
    """
    box: dict[str, float] = {"ms": 0.0}
    start = time.perf_counter()
    try:
        yield box
    finally:
        box["ms"] = round((time.perf_counter() - start) * 1000, 2)


def read_plan_summary(cur: sqlite3.Cursor, run_id: str) -> list[dict] | None:
    """读汇总表；表不存在、该 run 没行、行数没覆盖全部计划时一律返回 None（调用方回退在线聚合）。

    完整性用“汇总行数 == 该 run 年度 plan 行数”判断，避免汇总表只刷了部分批次时
    把“该批有 2 个计划”静默报成 0 个计划。所以汇总表必须为 plan **全量**写行，
    未执行的批次也要写 admitted_count=0 的行（见 `docs/04` 第 9 节）。
    """
    cols = ", ".join(SUMMARY_COLUMNS)
    sql = f"SELECT {cols} FROM {SUMMARY_TABLE} WHERE run_id = ? ORDER BY batch, plan_id"
    try:
        rows = cur.execute(sql, (run_id,)).fetchall()
    except sqlite3.Error:  # 表还没建（2 号未交付）或列名不符，都回退
        return None
    if not rows:
        return None
    if not _covers_all_plans(cur, run_id, len(rows)):
        return None

    items = []
    for r in rows:
        items.append({
            "plan_id": r["plan_id"],
            "batch": r["batch"],
            "category": r["category"],
            "school_id": r["school_id"],
            "school_name": r["school_name"],
            "quota": int(r["quota"] or 0),
            "carry_in": int(r["carry_in"] or 0),
            "quota_total": int(r["quota_total"] or 0),
            "admitted_count": int(r["admitted_count"] or 0),
            "remaining": int(r["remaining"] or 0),
            "min_score": r["min_score"],
            "max_score": r["max_score"],
            "last_admitted": {
                "student_id": r["last_student_id"],
                "score": r["last_score"],
                "tie_seq": r["last_tie_seq"],
                "volunteer_no": r["last_volunteer_no"],
                "admit_order": r["last_admit_order"],
            } if r["last_admit_order"] is not None else None,
        })
    return items


def _covers_all_plans(cur: sqlite3.Cursor, run_id: str, summary_rows: int) -> bool:
    """汇总行数是否覆盖该 run 年度的全部计划；判断不了就按“不覆盖”处理（宁可慢，不可错）。"""
    try:
        row = cur.execute(
            "SELECT COUNT(*) AS c FROM plan "
            "WHERE year = (SELECT year FROM run WHERE run_id = ?)", (run_id,)).fetchone()
        total = int(row["c"] or 0)
    except sqlite3.Error:
        return False
    return total == summary_rows


# 刷新用 SQL：两句分开执行（命名参数，3 号在 store.write_results 末尾调用）
DELETE_SQL = f"DELETE FROM {SUMMARY_TABLE} WHERE run_id = :run_id"

INSERT_SQL = f"""INSERT INTO {SUMMARY_TABLE} (
    run_id, plan_id, batch, category, school_id, school_name,
    quota, carry_in, quota_total, admitted_count, remaining, min_score, max_score,
    last_student_id, last_score, last_tie_seq, last_volunteer_no, last_admit_order)
SELECT :run_id, p.plan_id, p.batch, p.category, p.high_school_id, h.name,
       p.quota,
       COALESCE(c.amt, 0),
       p.quota + COALESCE(c.amt, 0),
       COALESCE(a.cnt, 0),
       COALESCE(p.remaining, p.quota + COALESCE(c.amt, 0) - COALESCE(a.cnt, 0)),
       a.min_score, a.max_score,
       l.student_id, l.score, l.tie_seq, l.volunteer_no, l.admit_order
FROM plan p
LEFT JOIN high_school h ON h.school_id = p.high_school_id
LEFT JOIN (SELECT to_plan_id, SUM(amount) AS amt FROM carry_log
           WHERE run_id = :run_id GROUP BY to_plan_id) c
       ON c.to_plan_id = p.plan_id
LEFT JOIN (SELECT plan_id, COUNT(*) AS cnt, MIN(score) AS min_score, MAX(score) AS max_score
           FROM admit_result WHERE run_id = :run_id GROUP BY plan_id) a
       ON a.plan_id = p.plan_id
LEFT JOIN (SELECT r1.plan_id, r1.student_id, r1.score, r1.tie_seq,
                  r1.volunteer_no, r1.admit_order
           FROM admit_result r1
           JOIN (SELECT plan_id, MAX(admit_order) AS mo FROM admit_result
                 WHERE run_id = :run_id GROUP BY plan_id) m
             ON m.plan_id = r1.plan_id AND m.mo = r1.admit_order
           WHERE r1.run_id = :run_id) l
       ON l.plan_id = p.plan_id
WHERE p.year = :year"""


def summary_delete_sql() -> str:
    """刷新第一步：清掉该 run 的旧汇总行（交 3 号，4 号不写库）。"""
    return DELETE_SQL


def summary_insert_sql() -> str:
    """刷新第二步：按 plan 全量重算并写入（命名参数 `run_id`、`year`）。

    覆盖全部计划（该年度每一条 plan 一行），所以未执行批次也有 `admitted_count = 0` 的行，
    满足 `read_plan_summary()` 的完整性校验；无人录取的 `min_score` / `last_*` 为 NULL。
    """
    return INSERT_SQL


def summary_ddl() -> str:
    """汇总表 DDL 文本（交 2 号执行，4 号不建表）。

    列含义：
    - `quota_total = quota + carry_in`（R27 有效计划数）；
    - `remaining` 取 `plan.remaining`；
    - `last_*` 为末位考生快照（R31），无人录取时全部为 NULL，由调用方输出 None/“无”。
    """
    return f"""-- 统计汇总表（4 号给出定义，2 号建表并在 write_results 后刷新）
CREATE TABLE IF NOT EXISTS {SUMMARY_TABLE} (
    run_id           TEXT    NOT NULL,
    plan_id          TEXT    NOT NULL,
    batch            INTEGER NOT NULL,
    category         TEXT,
    school_id        TEXT,
    school_name      TEXT,
    quota            INTEGER NOT NULL DEFAULT 0,
    carry_in         INTEGER NOT NULL DEFAULT 0,
    quota_total      INTEGER NOT NULL DEFAULT 0,
    admitted_count   INTEGER NOT NULL DEFAULT 0,
    remaining        INTEGER NOT NULL DEFAULT 0,
    min_score        INTEGER,
    max_score        INTEGER,
    last_student_id  TEXT,
    last_score       INTEGER,
    last_tie_seq     INTEGER,
    last_volunteer_no INTEGER,
    last_admit_order INTEGER,
    PRIMARY KEY (run_id, plan_id)
);"""


# 建议索引：固定索引名，便于 missing_indexes() 判断是否已建
INDEX_DDL: tuple[tuple[str, str], ...] = (
    ("idx_admit_result_run_plan_order", "admit_result (run_id, plan_id, admit_order)"),
    ("idx_admit_result_run_student", "admit_result (run_id, student_id)"),
    ("idx_admit_result_run_batch", "admit_result (run_id, batch)"),
    ("idx_admit_log_run_student", "admit_log (run_id, student_id)"),
    ("idx_volunteer_student_year", "volunteer (student_id, year, batch, seq)"),
    ("idx_plan_school_batch", "plan (high_school_id, batch)"),
    ("idx_carry_log_run_plan", "carry_log (run_id, to_plan_id)"),
)


def index_ddl() -> list[str]:
    """建议索引的 CREATE INDEX 文本（交 2 号执行；4 号只读库，不建索引）。"""
    return [f"CREATE INDEX IF NOT EXISTS {name} ON {target};" for name, target in INDEX_DDL]


def missing_indexes(conn: sqlite3.Connection) -> list[str]:
    """返回尚未建立的建议索引名；空列表表示三类查询都有覆盖索引可用。"""
    try:
        found = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()}
    except sqlite3.Error:
        return [name for name, _ in INDEX_DDL]
    return [name for name, _ in INDEX_DDL if name not in found]
