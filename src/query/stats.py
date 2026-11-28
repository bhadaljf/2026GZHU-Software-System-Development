"""统计口径（4 号：黎俊彤）。

职责：批次统计、学校统计、分数分布（docs/09 第 3 节 4 号第三、四行）。
入参：run_id、batch 或 school_id；可选 conn、mock
出参：dict

口径约定（R30/R31/R32/R33）：
- 完成率 = 已录人数 / 有效计划数（有效计划数 = 初始计划 + 转入），除数为 0 时按 0 处理；
- 最低录取分按计划算，计划无人录取则不计入批次最低分；全批无人录取返回 None（界面显示“无”）；
- 学校总体与分批、分类计划分开算（R33），三套口径不混算；
- 未完成名额 = max(有效计划数 − 已录, 0)；未完成计划 = 剩余名额 > 0 的计划数。
"""

from __future__ import annotations

import sqlite3

try:
    from src.query import open_cursor, use_mock
    from src.query import mockdata as _mock
    from src.query.perf import read_plan_summary
except ImportError:
    from query import open_cursor, use_mock
    from query import mockdata as _mock
    from query.perf import read_plan_summary


# ---------------------------------------------------------------- 批次统计

def get_batch_stats(run_id: str, batch: int, *, conn=None, mock=None) -> dict:
    """某一批次的计划数、录取数、完成率、未录人数、最低/最高录取分。"""
    batch = int(batch)
    if use_mock(mock):
        items = _mock_plan_items(batch=batch)
        volunteered, unadmitted = _mock_volunteer_counts(batch)
        source = "mock"
    else:
        with open_cursor(conn) as cur:
            items, source = _plan_items(cur, run_id, batch=batch, with_source=True)
            volunteered = _count_volunteered(cur, batch)
            unadmitted = _count_unadmitted_in_batch(cur, run_id, batch)

    out = {"run_id": run_id, "batch": batch, "source": source}
    out.update(_aggregate(items))
    out["volunteered_students"] = volunteered
    out["unadmitted_students"] = unadmitted
    out["plans"] = [
        {"plan_id": i["plan_id"], "school": i["school_name"], "category": i["category"],
         "quota_total": i["quota_total"], "admitted_count": i["admitted_count"],
         "remaining": i["remaining"], "min_score": i["min_score"]}
        for i in items
    ]
    return out


# ---------------------------------------------------------------- 学校统计

def get_school_stats(run_id: str, school_id: str, *, conn=None, mock=None) -> dict:
    """某高中的总体统计 + 分批统计 + 分类统计（R33：三套口径分开）。"""
    if use_mock(mock):
        items = _mock_plan_items(school_id=school_id)
        school_name = next((s["name"] for s in _mock.SCHOOLS if s["school_id"] == school_id), None)
        source = "mock"
    else:
        with open_cursor(conn) as cur:
            items, source = _plan_items(cur, run_id, school_id=school_id, with_source=True)
            row = cur.execute("SELECT name FROM high_school WHERE school_id = ?",
                              (school_id,)).fetchone()
            school_name = row["name"] if row else None

    overall = _aggregate(items)
    return {
        "run_id": run_id,
        "school_id": school_id,
        "school": school_name,
        "exists": school_name is not None,
        "source": source,
        "overall": overall,
        "by_batch": [dict(batch=b, **_aggregate(v)) for b, v in
                     sorted(_group(items, "batch").items())],
        "by_category": [dict(category=c, **_aggregate(v)) for c, v in
                        sorted(_group(items, "category").items())],
        "plans": [
            {"plan_id": i["plan_id"], "batch": i["batch"], "category": i["category"],
             "quota_total": i["quota_total"], "admitted_count": i["admitted_count"],
             "remaining": i["remaining"], "min_score": i["min_score"],
             "last_admitted": i["last_admitted"]}
            for i in items
        ],
    }


# ---------------------------------------------------------------- 分数分布

def get_score_distribution(run_id: str, batch: int, bucket_size: int = 10,
                           *, conn=None, mock=None) -> dict:
    """已录考生按分数段（默认 10 分一段）的人数分布。"""
    batch = int(batch)
    bucket_size = max(int(bucket_size or 10), 1)

    if use_mock(mock):
        scores = [r["score"] for r in _mock.RESULTS if r["batch"] == batch]
        lines = _mock.RULES
        source = "mock"
    else:
        with open_cursor(conn) as cur:
            scores = [r["score"] for r in cur.execute(
                "SELECT score FROM admit_result WHERE run_id = ? AND batch = ?",
                (run_id, batch)).fetchall()]
            lines = _read_rules()
        source = "online"

    buckets: dict[int, int] = {}
    for s in scores:
        low = (int(s) // bucket_size) * bucket_size
        buckets[low] = buckets.get(low, 0) + 1

    return {
        "run_id": run_id,
        "batch": batch,
        "source": source,
        "bucket_size": bucket_size,
        "buckets": [
            {"label": f"{low}-{low + bucket_size - 1}", "low": low,
             "high": low + bucket_size - 1, "count": buckets[low]}
            for low in sorted(buckets, reverse=True)
        ],
        "total": len(scores),
        "min_score": min(scores) if scores else None,
        "max_score": max(scores) if scores else None,
        "lines": {
            "control_line": lines.get("control_line"),
            "gradient_first": lines.get("gradient", {}).get("first_line"),
            "gradient_delta": lines.get("gradient", {}).get("delta"),
        },
    }


# ---------------------------------------------------------------- 内部实现

def _plan_items(cur: sqlite3.Cursor, run_id: str, batch: int | None = None,
                school_id: str | None = None, *, with_source: bool = False):
    """取计划 + 该计划的已录汇总 + 转入名额，拼成统一的行结构。

    第二阶段：先读汇总表 `plan_summary`（见 `src/query/perf.py`），命中就直接用，
    不再在线聚合 15 万条明细；汇总表还没建（2 号未交付）时自动回退在线聚合，行为不变。
    `with_source=True` 时多返回一个来源标记：`summary` / `online`。
    """
    summary = read_plan_summary(cur, run_id)
    if summary is not None:
        items = summary
        if batch is not None:
            items = [i for i in items if i["batch"] == batch]
        if school_id is not None:
            items = [i for i in items if i["school_id"] == school_id]
        # 汇总表可能只刷了部分批次/部分学校：过滤后为空就回退在线聚合，
        # 否则会把“该批有 2 个计划”静默报成 0 个计划，是不可接受的错数据。
        if (batch is not None or school_id is not None) and not items:
            items = None
        else:
            items = sorted(items, key=lambda i: (i["batch"], i["plan_id"]))
            return (items, "summary") if with_source else items

    sql = ("SELECT p.plan_id, p.batch, p.category, p.quota, p.remaining, "
           "       p.high_school_id, h.name AS school_name "
           "FROM plan p LEFT JOIN high_school h ON h.school_id = p.high_school_id")
    where, args = [], []
    if batch is not None:
        where.append("p.batch = ?")
        args.append(batch)
    if school_id is not None:
        where.append("p.high_school_id = ?")
        args.append(school_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY p.batch, p.plan_id"
    plans = cur.execute(sql, args).fetchall()

    res = {r["plan_id"]: r for r in cur.execute(
        "SELECT plan_id, COUNT(*) AS cnt, MIN(score) AS min_score, MAX(score) AS max_score "
        "FROM admit_result WHERE run_id = ? GROUP BY plan_id", (run_id,)).fetchall()}
    carry = _carry_map(cur, run_id)
    last = _last_admitted_map(cur, run_id)

    items = []
    for p in plans:
        r = res.get(p["plan_id"])
        admitted = int(r["cnt"]) if r else 0
        quota = int(p["quota"] or 0)
        quota_total = quota + carry.get(p["plan_id"], 0)
        remaining = int(p["remaining"]) if p["remaining"] is not None else quota_total - admitted
        items.append({
            "plan_id": p["plan_id"],
            "batch": p["batch"],
            "category": p["category"],
            "school_id": p["high_school_id"],
            "school_name": p["school_name"],
            "quota": quota,
            "carry_in": carry.get(p["plan_id"], 0),
            "quota_total": quota_total,
            "admitted_count": admitted,
            "remaining": remaining,
            "min_score": r["min_score"] if r else None,
            "max_score": r["max_score"] if r else None,
            "last_admitted": last.get(p["plan_id"]),
        })
    return (items, "online") if with_source else items


def _carry_map(cur: sqlite3.Cursor, run_id: str) -> dict[str, int]:
    """plan_id -> 转入名额（carry_log 可能还没建表，容错为 0）。"""
    try:
        rows = cur.execute(
            "SELECT to_plan_id, COALESCE(SUM(amount), 0) AS amt FROM carry_log "
            "WHERE run_id = ? GROUP BY to_plan_id", (run_id,)).fetchall()
        return {r["to_plan_id"]: int(r["amt"] or 0) for r in rows}
    except sqlite3.Error:
        return {}


def _last_admitted_map(cur: sqlite3.Cursor, run_id: str) -> dict[str, dict]:
    """plan_id -> 末位考生（admit_order 最大者，R31）。"""
    try:
        rows = cur.execute(
            "SELECT plan_id, student_id, score, tie_seq, volunteer_no, admit_order "
            "FROM admit_result WHERE run_id = ? "
            "AND admit_order = (SELECT MAX(admit_order) FROM admit_result x "
            "                   WHERE x.run_id = admit_result.run_id "
            "                   AND x.plan_id = admit_result.plan_id)",
            (run_id,)).fetchall()
        return {r["plan_id"]: {
            "student_id": r["student_id"], "score": r["score"], "tie_seq": r["tie_seq"],
            "volunteer_no": r["volunteer_no"], "admit_order": r["admit_order"]} for r in rows}
    except sqlite3.Error:
        return {}


def _aggregate(items: list[dict]) -> dict:
    """一组计划汇总成统计字段（完成率、未完成名额等）。"""
    plan_count = len(items)
    quota_total = sum(i["quota_total"] for i in items)
    admitted = sum(i["admitted_count"] for i in items)
    remaining = sum(i["remaining"] for i in items)
    unfilled_plans = sum(1 for i in items if i["remaining"] > 0)
    min_scores = [i["min_score"] for i in items if i["min_score"] is not None]
    max_scores = [i["max_score"] for i in items if i["max_score"] is not None]
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
        "min_score": min(min_scores) if min_scores else None,
        "max_score": max(max_scores) if max_scores else None,
    }


def _group(items: list[dict], key: str) -> dict:
    """按某个字段分组（batch / category）。"""
    out: dict = {}
    for i in items:
        out.setdefault(i[key], []).append(i)
    return out


def _count_volunteered(cur: sqlite3.Cursor, batch: int) -> int:
    """该批填报了志愿的考生人数（按人去重，不是志愿条数）。"""
    try:
        row = cur.execute(
            "SELECT COUNT(DISTINCT student_id) AS c FROM volunteer WHERE batch = ?",
            (batch,)).fetchone()
        return int(row["c"] or 0)
    except sqlite3.Error:
        return 0


def _count_unadmitted_in_batch(cur: sqlite3.Cursor, run_id: str, batch: int) -> int:
    """该批填报了志愿、但本批没被录取的人数（R34：可再按原因码细分）。"""
    sql = ("SELECT COUNT(*) AS c FROM ("
           "  SELECT DISTINCT student_id FROM volunteer WHERE batch = ? "
           "  EXCEPT "
           "  SELECT DISTINCT student_id FROM admit_result WHERE run_id = ? AND batch = ?"
           ")")
    try:
        row = cur.execute(sql, (batch, run_id, batch)).fetchone()
        return int(row["c"] or 0)
    except sqlite3.Error:
        return 0


def _read_rules() -> dict:
    """读 config/rules.toml 的核心参数（只用于展示参考线，读不到就给空 dict）。"""
    try:
        import tomllib
        from src.query import BASE_DIR
    except ImportError:
        try:
            import tomllib
            from query import BASE_DIR
        except ImportError:
            return {}
    try:
        with open(BASE_DIR / "config" / "rules.toml", "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


# ---------------------------------------------------------------- mock 分支

def _mock_plan_items(batch: int | None = None, school_id: str | None = None) -> list[dict]:
    """mock：把假计划与假结果汇总成与 DB 分支同样的行结构。"""
    items = []
    for p in _mock.PLANS:
        if batch is not None and p["batch"] != batch:
            continue
        if school_id is not None and p["high_school_id"] != school_id:
            continue
        rows = sorted([r for r in _mock.RESULTS if r["plan_id"] == p["plan_id"]],
                      key=lambda r: r["admit_order"])
        school = _mock.school_of_plan(p["plan_id"])
        last = rows[-1] if rows else None
        items.append({
            "plan_id": p["plan_id"],
            "batch": p["batch"],
            "category": p["category"],
            "school_id": p["high_school_id"],
            "school_name": school["name"] if school else None,
            "quota": p["quota"],
            "carry_in": 0,
            "quota_total": p["quota"],
            "admitted_count": len(rows),
            "remaining": p["remaining"],
            "min_score": min((r["score"] for r in rows), default=None),
            "max_score": max((r["score"] for r in rows), default=None),
            "last_admitted": {
                "student_id": last["student_id"], "score": last["score"],
                "tie_seq": last["tie_seq"], "volunteer_no": last["volunteer_no"],
                "admit_order": last["admit_order"]} if last else None,
        })
    return items


def _mock_volunteer_counts(batch: int) -> tuple[int, int]:
    """mock：该批填报人数 与 填报了但本批未被录取的人数。"""
    volunteered = {v["student_id"] for v in _mock.VOLUNTEERS if v["batch"] == batch}
    admitted = {r["student_id"] for r in _mock.RESULTS if r["batch"] == batch}
    return len(volunteered), len(volunteered - admitted)
