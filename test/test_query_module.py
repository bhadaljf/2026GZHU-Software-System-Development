"""4 号查询统计模块自测（4 号：黎俊彤）。

与 5 号的验收用例（`test/test_query.py`、`test/cases/`）不冲突：
- 5 号那套对着引擎的 `expected.json` 判对错；
- 本文件只看 4 号自己这一层：返回结构是否与 `docs/00_契约.md`、`docs/08` 第 6 节一致，
  口径是否按 `docs/04_接口与统计口径.md` 执行，边界与异常是否不崩。

跑法（仓库根目录，不需要 pytest）：
    python test/test_query_module.py            # 全部用例
    python test/test_query_module.py -v         # 看每条用例名
    python -m unittest test.test_query_module   # 同上（需先有 test/__init__.py）

覆盖：
A. mock 分支（库没建好时 6 号能联调的那条路）：结构、min_score≠末位考生、无人录取为 None、分页纠正；
B. 真实库分支：用临时库按契约字段建表灌数据，验 SQL 与统计口径、carry_in、remaining、分布分桶、导出；
C. 只读约束、库未就绪判断、汇总表优先与在线回退、守恒不一致检测、错误输入；
D. CSV：列头固定、UTF-8 BOM、空值写“无”、口径说明文件随导出生成。
"""

from __future__ import annotations

import csv
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.export.export_csv import (  # noqa: E402
    ADMISSION_COLUMNS,
    STAT_COLUMNS,
    export_admissions,
    export_stats,
)
from src.query import connect, is_db_ready  # noqa: E402
from src.query.perf import (  # noqa: E402
    INDEX_DDL,
    index_ddl,
    missing_indexes,
    summary_ddl,
    summary_delete_sql,
    summary_insert_sql,
    timed,
)
from src.query.plan import get_plan_admissions  # noqa: E402
from src.query.reasons import (  # noqa: E402
    REASON_CODES,
    all_reasons,
    describe,
    is_valid,
)
from src.query.stats import (  # noqa: E402
    get_batch_stats,
    get_score_distribution,
    get_school_stats,
)
from src.query.student import get_student_result  # noqa: E402
from src.report.report import build_stats_report  # noqa: E402

RUN = "RUN-TEST-01"

# ---------------------------------------------------------------- 临时库夹具
# 字段严格照 docs/00_契约.md 第 1、2 节，不额外加字段
DDL = """
CREATE TABLE middle_school (school_id TEXT PRIMARY KEY, name TEXT NOT NULL, district TEXT);
CREATE TABLE high_school (school_id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT, recruit_batch INTEGER);
CREATE TABLE student (
    student_id TEXT PRIMARY KEY, name TEXT, junior_school_id TEXT,
    score INTEGER NOT NULL, tie_seq INTEGER NOT NULL);
CREATE TABLE plan (
    plan_id TEXT PRIMARY KEY, year INTEGER NOT NULL, high_school_id TEXT NOT NULL,
    batch INTEGER NOT NULL, category TEXT NOT NULL, quota INTEGER NOT NULL,
    control_line INTEGER, remaining INTEGER);
CREATE TABLE quota_plan (plan_id TEXT, junior_school_id TEXT, quota INTEGER);
CREATE TABLE self_recruit_eligibility (student_id TEXT, high_school_id TEXT, status TEXT, rank INTEGER);
CREATE TABLE volunteer (year INTEGER, student_id TEXT, batch INTEGER, seq INTEGER, plan_id TEXT);
CREATE TABLE run (
    run_id TEXT PRIMARY KEY, year INTEGER, params_json TEXT,
    data_version TEXT, operator TEXT, created_at TEXT);
CREATE TABLE admit_result (
    result_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, student_id TEXT NOT NULL,
    plan_id TEXT NOT NULL, batch INTEGER NOT NULL, volunteer_no INTEGER,
    admit_order INTEGER, score INTEGER, tie_seq INTEGER);
CREATE TABLE admit_log (
    log_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, batch INTEGER, band INTEGER,
    volunteer_no INTEGER, plan_id TEXT, student_id TEXT, action TEXT,
    reason_code TEXT, balance_before INTEGER, balance_after INTEGER, note TEXT);
CREATE TABLE carry_log (
    carry_id TEXT PRIMARY KEY, run_id TEXT, from_batch INTEGER, to_plan_id TEXT,
    high_school_id TEXT, amount INTEGER, source_note TEXT, created_at TEXT);
"""

MIDDLE = [("M01", "M 一中", "A 区"), ("M02", "M 二中", "B 区")]
HIGH = [("H01", "A 校", "public", 3), ("H02", "B 校", "public", 3), ("H03", "C 校", "public", 4)]
STUDENTS = [
    ("S01", "甲", "M01", 690, 1),
    ("S02", "乙", "M01", 710, 1),
    ("S03", "丙", "M02", 700, 2),
    ("S04", "丁", "M02", 655, 5),
    ("S05", "戊", "M01", 480, 9),
    ("S06", "己", "M01", 715, 1),
]
PLANS = [
    ("P-D1", 2026, "H02", 1, "self_recruit", 1, 600, 1),
    ("P-C2", 2026, "H01", 2, "quota", 1, 492, 0),
    ("P-A3", 2026, "H01", 3, "unified", 2, 492, 0),
    ("P-B3", 2026, "H02", 3, "unified", 1, 680, 0),
    ("P-G3", 2026, "H03", 3, "unified", 1, 700, 1),
    ("P-E4", 2026, "H03", 4, "unified", 2, 492, 2),
    ("P-X4", 2026, "H03", 4, "unified", 3, 492, 4),  # 有 1 个转入名额，有效计划 4
]
VOLUNTEERS = [
    (2026, "S01", 3, 1, "P-A3"), (2026, "S01", 3, 2, "P-B3"), (2026, "S01", 4, 1, "P-E4"),
    (2026, "S02", 3, 1, "P-B3"), (2026, "S02", 3, 2, "P-A3"),
    (2026, "S03", 2, 1, "P-C2"), (2026, "S03", 3, 1, "P-A3"),
    (2026, "S04", 3, 1, "P-B3"), (2026, "S04", 3, 2, "P-G3"),
    (2026, "S05", 1, 1, "P-D1"), (2026, "S05", 3, 1, "P-A3"),
    (2026, "S05", 3, 2, "P-B3"), (2026, "S05", 4, 1, "P-E4"),
    (2026, "S06", 3, 1, "P-B3"),
]
RESULTS = [
    ("RUN-TEST-01-2-P-C2-1", "S03", "P-C2", 2, 1, 1, 700, 2),
    ("RUN-TEST-01-3-P-A3-1", "S01", "P-A3", 3, 1, 1, 690, 1),
    ("RUN-TEST-01-3-P-A3-2", "S02", "P-A3", 3, 2, 2, 710, 1),
    ("RUN-TEST-01-3-P-B3-1", "S06", "P-B3", 3, 1, 1, 715, 1),
]
LOGS = [
    # S01 三批第一志愿录取，同批第二志愿满，四批前批已录
    ("L01", 3, 2, 1, "P-A3", "S01", "admit", None, 2, 1),
    ("L02", 3, 2, 2, "P-B3", "S01", "skip", "R02", 0, 0),
    ("L03", 4, 2, 1, "P-E4", "S01", "skip", "R04", 2, 2),
    # S02 一志愿满、二志愿录取
    ("L04", 3, 1, 1, "P-B3", "S02", "skip", "R02", 0, 0),
    ("L05", 3, 1, 2, "P-A3", "S02", "admit", None, 1, 0),
    # S03 二批录取，三批记前批已录
    ("L06", 2, 2, 1, "P-C2", "S03", "admit", None, 1, 0),
    ("L07", 3, 2, 1, "P-A3", "S03", "skip", "R04", 1, 1),
    # S04 全部落空：一所满、一所未达线
    ("L08", 3, 2, 1, "P-B3", "S04", "skip", "R02", 0, 0),
    ("L09", 3, 2, 2, "P-G3", "S04", "skip", "R01", 1, 1),
    # S05 资格不符 + 低于控制线
    ("L10", 1, 1, 1, "P-D1", "S05", "skip", "R03", 1, 1),
    ("L11", 3, 0, 1, "P-A3", "S05", "skip", "R01", 1, 1),
    ("L12", 3, 0, 2, "P-B3", "S05", "skip", "R01", 0, 0),
    ("L13", 4, 0, 1, "P-E4", "S05", "skip", "R01", 2, 2),
    # S06 录取
    ("L14", 3, 1, 1, "P-B3", "S06", "admit", None, 1, 0),
]

# 汇总表必须覆盖 plan 全量行（未执行批次写 0 值行），否则 stats 会回退在线聚合
SUMMARY_ROWS = [
    # run_id, plan_id, batch, category, school_id, school_name, quota, carry_in,
    # quota_total, admitted_count, remaining, min_score, max_score,
    # last_student_id, last_score, last_tie_seq, last_volunteer_no, last_admit_order
    (RUN, "P-D1", 1, "self_recruit", "H02", "B 校", 1, 0, 1, 0, 1, None, None, None, None, None, None, None),
    (RUN, "P-C2", 2, "quota", "H01", "A 校", 1, 0, 1, 1, 0, 700, 700, "S03", 700, 2, 1, 1),
    (RUN, "P-A3", 3, "unified", "H01", "A 校", 2, 0, 2, 2, 0, 690, 710, "S02", 710, 1, 2, 2),
    (RUN, "P-B3", 3, "unified", "H02", "B 校", 1, 0, 1, 1, 0, 715, 715, "S06", 715, 1, 1, 1),
    (RUN, "P-G3", 3, "unified", "H03", "C 校", 1, 0, 1, 0, 1, None, None, None, None, None, None, None),
    (RUN, "P-E4", 4, "unified", "H03", "C 校", 2, 0, 2, 0, 2, None, None, None, None, None, None, None),
    (RUN, "P-X4", 4, "unified", "H03", "C 校", 3, 1, 4, 0, 4, None, None, None, None, None, None, None),
]


def _exec(cur, sql, rows):
    for r in rows:
        cur.execute(sql, r)


def build_db(path: Path, *, with_summary: bool = False, break_conservation: bool = False) -> None:
    """按契约字段建一个临时小库；break_conservation=True 时故意让余额对不上。"""
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(DDL)
        cur = conn.cursor()
        _exec(cur, "INSERT INTO middle_school VALUES (?,?,?)", MIDDLE)
        _exec(cur, "INSERT INTO high_school VALUES (?,?,?,?)", HIGH)
        _exec(cur, "INSERT INTO student VALUES (?,?,?,?,?)", STUDENTS)
        plans = [list(p) for p in PLANS]
        if break_conservation:  # 有效计划 2、已录 2，却写剩余 1，守恒必然对不上
            plans = [[p[0], p[1], p[2], p[3], p[4], p[5], p[6],
                      1 if p[0] == "P-A3" else p[7]] for p in plans]
        _exec(cur, "INSERT INTO plan VALUES (?,?,?,?,?,?,?,?)", plans)
        _exec(cur, "INSERT INTO quota_plan VALUES (?,?,?)", [("P-C2", "M02", 1)])
        _exec(cur, "INSERT INTO self_recruit_eligibility VALUES (?,?,?,?)",
              [("S01", "H02", "eligible", 2)])
        _exec(cur, "INSERT INTO volunteer VALUES (?,?,?,?,?)", VOLUNTEERS)
        _exec(cur, "INSERT INTO run VALUES (?,?,?,?,?,?)",
              [(RUN, 2026, '{"control_line": 492}', "small-v1", "4",
                "2026-11-28T10:00:00+08:00")])
        _exec(cur, "INSERT INTO admit_result VALUES (?,?,?,?,?,?,?,?,?)",
              [(r[0], RUN, r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in RESULTS])
        _exec(cur, "INSERT INTO admit_log VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
              [(l[0], RUN, l[1], l[2], l[3], l[4], l[5], l[6], l[7], l[8], l[9], "") 
               for l in LOGS])
        _exec(cur, "INSERT INTO carry_log VALUES (?,?,?,?,?,?,?,?)",
              [("C-01", RUN, 3, "P-X4", "H03", 1, "三批余缺转入", "2026-11-28T10:05:00+08:00")])
        if with_summary:
            conn.executescript(summary_ddl())
            cur.executemany("INSERT INTO plan_summary VALUES " + "(" + ",".join(["?"] * 18) + ")",
                            SUMMARY_ROWS)
        conn.commit()
    finally:
        conn.close()


class _DbCase(unittest.TestCase):
    """每个用例一个独立临时库，避免互相影响。"""

    with_summary = False
    break_conservation = False

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "app.db"
        build_db(self.db, with_summary=self.with_summary,
                 break_conservation=self.break_conservation)
        self.conn = connect(self.db)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def q(self, fn, *args, **kw):
        return fn(*args, conn=self.conn, mock=False, **kw)


# ================================================================ A. mock 分支

class MockTests(unittest.TestCase):
    """库没建好时 6 号联调走的那条路（mock=True）。"""

    def test_01_考生返回结构包含契约字段(self):
        r = get_student_result("RUN-MOCK", "S01", mock=True)
        for k in ("run_id", "student_id", "score", "tie_seq", "admitted", "batch",
                  "plan_id", "school", "volunteer_no", "admit_order", "volunteers"):
            self.assertIn(k, r)
        self.assertTrue(r["admitted"])
        self.assertEqual(r["plan_id"], "P-A3")
        self.assertTrue(all(
            {"batch", "seq", "plan_id", "status", "reason_code"} <= set(v)
            for v in r["volunteers"]))

    def test_02_未录取者原因码取最后一个被跳过志愿(self):
        r = get_student_result("RUN-MOCK", "S05", mock=True)
        self.assertFalse(r["admitted"])
        self.assertIsNone(r["batch"])
        self.assertIsNone(r["volunteer_no"])
        self.assertEqual(r["reason_code"], "R01")
        self.assertEqual(r["reason_text"], "未达计划控制线或最低控制线")

    def test_03_最低分与末位考生可以不是同一人(self):
        r = get_plan_admissions("RUN-MOCK", "P-A3", mock=True)
        self.assertEqual(r["min_score"], 690)
        self.assertEqual(r["last_admitted"]["student_id"], "S02")
        self.assertEqual(r["last_admitted"]["score"], 710)
        self.assertNotEqual(r["min_score"], r["last_admitted"]["score"])

    def test_04_无人录取返回None而不是0(self):
        r = get_plan_admissions("RUN-MOCK", "P-G3", mock=True)
        self.assertIsNone(r["min_score"])
        self.assertIsNone(r["last_admitted"])
        self.assertIsNone(r["max_score"])
        self.assertEqual(r["items"], [])
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["total_pages"], 1)

    def test_05_分页参数越界自动纠正(self):
        r = get_plan_admissions("RUN-MOCK", "P-A3", page=0, size=0, mock=True)
        self.assertEqual(r["page"], 1)
        self.assertGreaterEqual(r["size"], 1)
        big = get_plan_admissions("RUN-MOCK", "P-A3", page=99, size=999, mock=True)
        self.assertEqual(big["size"], 500)
        self.assertEqual(big["items"], [])
        self.assertEqual(big["total"], 2)

    def test_06_考生与计划不存在给出exists为假(self):
        s = get_student_result("RUN-MOCK", "S99", mock=True)
        self.assertFalse(s["exists"])
        self.assertIsNone(s["score"])
        self.assertEqual(s["volunteers"], [])
        p = get_plan_admissions("RUN-MOCK", "P-XXXX", mock=True)
        self.assertFalse(p["exists"])
        self.assertEqual(p["items"], [])

    def test_07_批次统计口径(self):
        r = get_batch_stats("RUN-MOCK", 3, mock=True)
        self.assertEqual(r["source"], "mock")
        self.assertEqual(r["plan_count"], 3)
        self.assertEqual(r["quota_total"], 4)
        self.assertEqual(r["admitted_count"], 3)
        self.assertAlmostEqual(r["completion_rate"], 0.75, places=4)
        self.assertEqual(r["completion_rate_text"], "75.00%")
        self.assertEqual(r["unfilled_quota"], 1)
        self.assertEqual(r["unfilled_plans"], 1)
        self.assertEqual(r["min_score"], 690)
        self.assertEqual(r["max_score"], 715)

    def test_08_分数分布按已录考生分桶(self):
        r = get_score_distribution("RUN-MOCK", 3, mock=True)
        self.assertEqual(r["total"], 3)
        self.assertEqual(r["min_score"], 690)
        self.assertEqual(r["max_score"], 715)
        buckets = {b["label"]: b["count"] for b in r["buckets"]}
        self.assertEqual(buckets.get("690-699"), 1)
        self.assertEqual(buckets.get("710-719"), 2)
        self.assertEqual([b["low"] for b in r["buckets"]], [710, 690])  # 降序

    def test_09_学校统计三套口径分开(self):
        r = get_school_stats("RUN-MOCK", "H01", mock=True)
        self.assertTrue(r["exists"])
        self.assertEqual(r["overall"]["plan_count"], 2)
        self.assertEqual({b["batch"] for b in r["by_batch"]}, {2, 3})
        self.assertEqual({c["category"] for c in r["by_category"]}, {"quota", "unified"})

    def test_10_报表守恒核对无差异(self):
        r = build_stats_report("RUN-MOCK", mock=True)
        self.assertEqual(r["conservation"]["mismatch"], 0)
        self.assertEqual(r["conservation"]["checked"], 6)
        self.assertTrue(r["notes"])


# ================================================================ B. 真实库分支

class DbStudentPlanTests(_DbCase):
    """考生查询与计划名单：SQL 分支与契约口径。"""

    def test_11_库就绪判断(self):
        self.assertTrue(is_db_ready(self.db))
        self.assertFalse(is_db_ready(self.db.parent / "nope.db"))

    def test_12_只读连接拒绝写入(self):
        ro = connect(self.db, read_only=True)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                ro.execute("INSERT INTO student VALUES ('SX','x','M01',1,1)")
        finally:
            ro.close()

    def test_13_已录取考生各志愿判定(self):
        r = self.q(get_student_result, RUN, "S01")
        self.assertTrue(r["admitted"])
        self.assertEqual(r["batch"], 3)
        self.assertEqual(r["school"], "A 校")
        self.assertEqual(r["admit_order"], 1)
        self.assertEqual(len(r["volunteers"]), 3)
        by_seq = {(v["batch"], v["seq"]): v for v in r["volunteers"]}
        self.assertEqual(by_seq[(3, 1)]["status"], "admitted")
        self.assertEqual(by_seq[(3, 2)]["reason_code"], "R02")
        self.assertEqual(by_seq[(3, 2)]["reason_text"], "计划名额已满")
        self.assertEqual(by_seq[(4, 1)]["reason_code"], "R04")

    def test_14_前批录取者也写进志愿判定(self):
        r = self.q(get_student_result, RUN, "S03")
        self.assertTrue(r["admitted"])
        self.assertEqual(r["batch"], 2)
        by_seq = {(v["batch"], v["seq"]): v["status"] for v in r["volunteers"]}
        self.assertEqual(by_seq[(2, 1)], "admitted")
        self.assertEqual(by_seq[(3, 1)], "skipped")

    def test_15_未录取考生原因可区分(self):
        r = self.q(get_student_result, RUN, "S05")
        self.assertFalse(r["admitted"])
        self.assertIsNone(r["batch"])
        self.assertEqual(r["reason_code"], "R01")
        self.assertEqual(len(r["volunteers"]), 4)
        self.assertEqual({v["reason_code"] for v in r["volunteers"]}, {"R01", "R03"})

    def test_16_查不到考生稳定返回(self):
        r = self.q(get_student_result, RUN, "S99")
        self.assertFalse(r["exists"])
        self.assertFalse(r["admitted"])
        self.assertEqual(r["volunteers"], [])

    def test_17_计划名单最低分末位考生与余额(self):
        r = self.q(get_plan_admissions, RUN, "P-A3")
        self.assertEqual(r["quota"], 2)
        self.assertEqual(r["quota_total"], 2)
        self.assertEqual(r["admitted_count"], 2)
        self.assertEqual(r["remaining"], 0)
        self.assertEqual(r["min_score"], 690)
        self.assertEqual(r["max_score"], 710)
        self.assertEqual(r["last_admitted"]["student_id"], "S02")
        self.assertEqual(r["last_admitted"]["volunteer_no"], 2)
        self.assertEqual([i["admit_order"] for i in r["items"]], [1, 2])

    def test_18_转入名额计入有效计划数(self):
        r = self.q(get_plan_admissions, RUN, "P-X4")
        self.assertEqual(r["carry_in"], 1)
        self.assertEqual(r["quota_total"], 4)  # 3 + 1
        self.assertEqual(r["remaining"], 4)
        self.assertIsNone(r["min_score"])
        self.assertIsNone(r["last_admitted"])
        self.assertEqual(r["items"], [])

    def test_19_计划分页与越界(self):
        r = self.q(get_plan_admissions, RUN, "P-A3", page=2, size=1)
        self.assertEqual(r["page"], 2)
        self.assertEqual(r["size"], 1)
        self.assertEqual(r["total"], 2)
        self.assertEqual(r["total_pages"], 2)
        self.assertEqual([i["admit_order"] for i in r["items"]], [2])  # 第 2 页是末位 S02
        r3 = self.q(get_plan_admissions, RUN, "P-A3", page=3, size=1)
        self.assertEqual(r3["items"], [])          # 超出总页数 -> 空列表但 total 不变
        self.assertEqual(r3["total"], 2)
        r0 = self.q(get_plan_admissions, RUN, "P-A3", page=0, size=0)
        self.assertEqual(r0["page"], 1)
        self.assertEqual(r0["size"], 100)

    def test_20_计划不存在(self):
        r = self.q(get_plan_admissions, RUN, "P-NONE")
        self.assertFalse(r["exists"])
        self.assertEqual(r["items"], [])
        self.assertEqual(r["total_pages"], 1)


class DbStatsTests(_DbCase):
    """批次、学校、分布、报表：统计口径与除零等边界。"""

    def test_21_批次统计与填报人数(self):
        r = self.q(get_batch_stats, RUN, 3)
        self.assertEqual(r["source"], "online")
        self.assertEqual(r["plan_count"], 3)
        self.assertEqual(r["quota_total"], 4)
        self.assertEqual(r["admitted_count"], 3)
        self.assertAlmostEqual(r["completion_rate"], 0.75, places=4)
        self.assertEqual(r["unfilled_quota"], 1)
        self.assertEqual(r["unfilled_plans"], 1)
        self.assertEqual(r["min_score"], 690)
        self.assertEqual(r["volunteered_students"], 6)   # 按人去重
        self.assertEqual(r["unadmitted_students"], 3)    # S03 前批已录、S04、S05
        self.assertEqual(len(r["plans"]), 3)

    def test_22_空批次不炸且完成率为0(self):
        r = self.q(get_batch_stats, RUN, 5)
        self.assertEqual(r["plan_count"], 0)
        self.assertEqual(r["quota_total"], 0)
        self.assertEqual(r["completion_rate"], 0.0)
        self.assertEqual(r["completion_rate_text"], "0.00%")
        self.assertIsNone(r["min_score"])

    def test_23_整批无人录取最低分为None(self):
        r = self.q(get_batch_stats, RUN, 1)
        self.assertEqual(r["admitted_count"], 0)
        self.assertIsNone(r["min_score"])
        self.assertIsNone(r["max_score"])

    def test_24_学校统计总体分批分类一致(self):
        r = self.q(get_school_stats, RUN, "H01")
        self.assertTrue(r["exists"])
        self.assertEqual(r["school"], "A 校")
        self.assertEqual(r["overall"]["plan_count"], 2)
        self.assertEqual(r["overall"]["admitted_count"], 3)
        self.assertAlmostEqual(r["overall"]["completion_rate"], 1.0, places=4)
        self.assertEqual(sum(b["admitted_count"] for b in r["by_batch"]), 3)
        self.assertEqual(sum(c["admitted_count"] for c in r["by_category"]), 3)
        self.assertEqual(r["overall"]["min_score"], 690)

    def test_25_学校不存在(self):
        r = self.q(get_school_stats, RUN, "H99")
        self.assertFalse(r["exists"])
        self.assertIsNone(r["school"])
        self.assertEqual(r["overall"]["plan_count"], 0)
        self.assertEqual(r["plans"], [])

    def test_26_分布分桶与参考线(self):
        r = self.q(get_score_distribution, RUN, 3)
        self.assertEqual(r["total"], 3)
        self.assertEqual(r["bucket_size"], 10)
        buckets = {b["label"]: b["count"] for b in r["buckets"]}
        self.assertEqual(buckets.get("690-699"), 1)
        self.assertEqual(buckets.get("710-719"), 2)
        self.assertEqual(r["lines"]["control_line"], 492)
        self.assertEqual(r["lines"]["gradient_first"], 712)
        self.assertEqual(r["lines"]["gradient_delta"], 40)

    def test_27_分布空批次(self):
        r = self.q(get_score_distribution, RUN, 1)
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["buckets"], [])
        self.assertIsNone(r["min_score"])
        self.assertIsNone(r["max_score"])

    def test_28_报表守恒核对通过(self):
        r = self.q(build_stats_report, RUN)
        self.assertEqual(r["conservation"]["mismatch"], 0)
        self.assertEqual(r["conservation"]["checked"], 7)
        self.assertEqual(r["overall"]["admitted_students"], 4)
        self.assertEqual(r["overall"]["volunteered_students"], 6)
        self.assertEqual(r["overall"]["unadmitted_students"], 2)
        self.assertEqual(r["run"]["data_version"], "small-v1")
        self.assertEqual(len(r["by_school"]), 3)


# ================================================================ C. 汇总表与索引

class DbSummaryTests(_DbCase):
    """第二阶段要求：统计优先读汇总表，表不在就回退在线聚合。"""

    with_summary = True

    def test_29_有汇总表时走汇总表且结果一致(self):
        r = self.q(get_batch_stats, RUN, 3)
        self.assertEqual(r["source"], "summary")
        for key, want in (("plan_count", 3), ("quota_total", 4), ("admitted_count", 3),
                          ("completion_rate", 0.75), ("unfilled_quota", 1),
                          ("unfilled_plans", 1), ("min_score", 690), ("max_score", 715)):
            self.assertEqual(r[key], want, msg=key)
        self.assertEqual(len(r["plans"]), 3)

    def test_30_汇总表的末位考生能带到学校统计(self):
        r = self.q(get_school_stats, RUN, "H01")
        self.assertEqual(r["source"], "summary")
        plan_a3 = next(p for p in r["plans"] if p["plan_id"] == "P-A3")
        self.assertEqual(plan_a3["last_admitted"]["student_id"], "S02")
        self.assertEqual(plan_a3["last_admitted"]["score"], 710)
        r3 = self.q(get_school_stats, RUN, "H03")
        plan_g3 = next(p for p in r3["plans"] if p["plan_id"] == "P-G3")
        self.assertIsNone(plan_g3["last_admitted"])
        self.assertIsNone(plan_g3["min_score"])

    def test_31_汇总表缺该批行时回退在线聚合(self):
        # 汇总表只刷了前三批，第四批没行 -> 必须回退在线聚合，不能报成 0 个计划
        writer = sqlite3.connect(str(self.db))
        try:
            writer.execute("DELETE FROM plan_summary WHERE batch = 4")
            writer.commit()
        finally:
            writer.close()
        r = self.q(get_batch_stats, RUN, 4)
        self.assertEqual(r["source"], "online")
        self.assertEqual(r["plan_count"], 2)
        self.assertEqual(r["quota_total"], 6)  # P-E4(2) + P-X4(3+1)

    def test_32_索引建议文本可执行且可核对(self):
        ddl = index_ddl()
        self.assertEqual(len(ddl), len(INDEX_DDL))
        self.assertTrue(all(s.startswith("CREATE INDEX IF NOT EXISTS") for s in ddl))
        conn = sqlite3.connect(str(self.db))
        try:
            conn.executescript("\n".join(ddl))
            self.assertEqual(missing_indexes(conn), [])
        finally:
            conn.close()

    def test_33_未建索引时报出清单(self):
        self.assertEqual(len(missing_indexes(self.conn)), len(INDEX_DDL))


class DbSummaryRefreshTests(_DbCase):
    """验证 4 号交给 3 号的刷新 SQL：按 plan 全量重算，结果必须与在线聚合一致。"""

    def _refresh(self):
        writer = sqlite3.connect(str(self.db))
        try:
            writer.executescript(summary_ddl())
            writer.execute(summary_delete_sql(), {"run_id": RUN})
            writer.execute(summary_insert_sql(), {"run_id": RUN, "year": 2026})
            writer.commit()
        finally:
            writer.close()

    def test_45_刷新SQL生成全量汇总且与在线一致(self):
        self._refresh()
        r3 = self.q(get_batch_stats, RUN, 3)
        self.assertEqual(r3["source"], "summary")
        self.assertEqual(r3["plan_count"], 3)
        self.assertEqual(r3["quota_total"], 4)
        self.assertEqual(r3["admitted_count"], 3)
        self.assertEqual(r3["min_score"], 690)
        self.assertEqual(r3["max_score"], 715)
        r4 = self.q(get_batch_stats, RUN, 4)
        self.assertEqual(r4["source"], "summary")   # 未执行批次也有 0 值行
        self.assertEqual(r4["quota_total"], 6)      # P-E4(2) + P-X4(3+1)
        self.assertEqual(r4["admitted_count"], 0)

    def test_46_刷新后末位考生与空值正确(self):
        self._refresh()
        h01 = self.q(get_school_stats, RUN, "H01")
        self.assertEqual(h01["source"], "summary")
        a3 = next(p for p in h01["plans"] if p["plan_id"] == "P-A3")
        self.assertEqual(a3["last_admitted"]["student_id"], "S02")
        self.assertEqual(a3["last_admitted"]["score"], 710)
        c2 = next(p for p in h01["plans"] if p["plan_id"] == "P-C2")
        self.assertEqual(c2["last_admitted"]["student_id"], "S03")
        h03 = self.q(get_school_stats, RUN, "H03")
        g3 = next(p for p in h03["plans"] if p["plan_id"] == "P-G3")
        self.assertIsNone(g3["min_score"])
        self.assertIsNone(g3["last_admitted"])
        x4 = next(p for p in h03["plans"] if p["plan_id"] == "P-X4")
        self.assertEqual(x4["quota_total"], 4)   # 3 + 转入 1


class DbBrokenTests(_DbCase):
    """故意让余额对不上，验证守恒核对能报出来（只报告，不改口径）。"""

    break_conservation = True

    def test_34_守恒不一致被检测到(self):
        r = self.q(build_stats_report, RUN)
        self.assertEqual(r["conservation"]["mismatch"], 1)
        bad = r["conservation"]["items"][0]
        self.assertEqual(bad["plan_id"], "P-A3")
        self.assertEqual(bad["expected_remaining"], 0)
        self.assertEqual(bad["remaining"], 1)


# ================================================================ D. 原因码与导出

class ReasonTests(unittest.TestCase):
    """码表是唯一出处，6 号渲染与 5 号对账都依赖它。"""

    EXPECTED = {
        "R01": "未达计划控制线或最低控制线",
        "R02": "计划名额已满",
        "R03": "不在自主招生资格名单或排名不达",
        "R04": "前批已录取",
        "R05": "非所属初中名额",
        "R06": "志愿或计划无效",
        "R07": "未填报该计划",
    }

    def test_35_码表与契约完全一致(self):
        self.assertEqual(REASON_CODES, self.EXPECTED)

    def test_36_all_reasons结构与适用批次(self):
        rs = all_reasons()
        self.assertEqual(len(rs), 7)
        self.assertEqual([r["code"] for r in rs], sorted(self.EXPECTED))
        for r in rs:
            self.assertEqual(r["text"], self.EXPECTED[r["code"]])
            self.assertTrue(all(b in (1, 2, 3, 4) for b in r["batches"]))
        r03 = next(r for r in rs if r["code"] == "R03")
        self.assertEqual(r03["batches"], [1])       # 自主招生只在第一批
        r05 = next(r for r in rs if r["code"] == "R05")
        self.assertEqual(r05["batches"], [2])       # 名额到校只在第二批

    def test_37_describe的空值与未知码(self):
        self.assertEqual(describe(None), "-")
        self.assertEqual(describe(""), "-")
        self.assertEqual(describe("r01"), self.EXPECTED["R01"])  # 大小写不敏感
        self.assertEqual(describe("R99"), "未知原因")
        self.assertTrue(is_valid("R07"))
        self.assertFalse(is_valid(None))
        self.assertFalse(is_valid("R99"))


class ExportTests(_DbCase):
    """导出：列头固定、BOM、空值写“无”、附口径说明（R35）。"""

    def test_38_录取CSV列头与行数(self):
        out = Path(self._tmp.name) / "adm.csv"
        p = export_admissions(RUN, str(out), conn=self.conn, mock=False)
        self.assertEqual(Path(p), out)
        raw = out.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))  # UTF-8 BOM
        with open(out, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], ADMISSION_COLUMNS)
        self.assertEqual(len(rows) - 1, 4)
        # 排序：批次 → 计划 → 录取顺序
        body = rows[1:]
        self.assertEqual([r[4] for r in body], ["2", "3", "3", "3"])

    def test_39_录取CSV附口径说明(self):
        out = Path(self._tmp.name) / "adm.csv"
        export_admissions(RUN, str(out), conn=self.conn, mock=False)
        note = out.with_name(out.stem + "_口径说明.md")
        self.assertTrue(note.exists())
        text = note.read_text(encoding="utf-8")
        self.assertIn(RUN, text)
        self.assertIn("空值一律写“无”", text)

    def test_40_统计CSV空值写无不是0(self):
        out = Path(self._tmp.name) / "stat.csv"
        export_stats(RUN, str(out), conn=self.conn, mock=False)
        with open(out, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], STAT_COLUMNS)
        dims = {r[0] for r in rows[1:]}
        self.assertTrue({"全校", "分批", "分类", "按校"} <= dims)
        batch1 = next(r for r in rows[1:] if r[0] == "分批" and r[1] == "第 1 批")
        self.assertEqual(batch1[8], "无")  # 最低录取分，整批无人录取
        self.assertNotEqual(batch1[8], "0")
        all_row = next(r for r in rows[1:] if r[0] == "全校")
        self.assertEqual(all_row[8], "690")  # 全校最低录取分

    def test_41_导出空结果不崩(self):
        out = Path(self._tmp.name) / "empty.csv"
        p = export_admissions("RUN-EMPTY", str(out), conn=self.conn, mock=False)
        with open(p, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows, [ADMISSION_COLUMNS])

    def test_42_mock导出可生成样例(self):
        p = export_admissions("RUN-MOCK", str(Path(self._tmp.name) / "mock.csv"), mock=True)
        self.assertTrue(Path(p).exists())


# ================================================================ E. 工具

class PerfTests(unittest.TestCase):
    """计时与 DDL 文本（第二阶段性能要求的最小支撑）。"""

    def test_43_timed返回毫秒(self):
        with timed() as box:
            sum(range(10000))
        self.assertIn("ms", box)
        self.assertGreaterEqual(box["ms"], 0.0)

    def test_44_汇总表DDL含全部列(self):
        ddl = summary_ddl()
        self.assertIn("CREATE TABLE IF NOT EXISTS plan_summary", ddl)
        for col in ("run_id", "quota_total", "min_score", "last_admit_order", "remaining"):
            self.assertIn(col, ddl)
        self.assertIn("PRIMARY KEY (run_id, plan_id)", ddl)


def main() -> int:
    return 0 if unittest.main(exit=False, verbosity=2).result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
