"""运行快照元数据（1 号）。

职责：为每次模拟运行创建唯一 run_id，并把参数快照、数据版本、执行人、时间写进
run 表，作为结果的追溯依据（R36、R37）。

入参：sqlite3 连接、年度、规则参数字典、数据版本、执行人。
出参：run_id 字符串，格式 RUN{YYYYMMDD}-{两位序号}。

表结构见 db/schema_run.sql；本模块不建主数据表，也不写结果表。
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema_run.sql"


def ensure_schema(conn: sqlite3.Connection) -> None:
    """建 run 表（幂等）。2 号的 init_db 也调用本函数，保证只有一份 DDL。"""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def create_run(
    conn: sqlite3.Connection,
    year: int,
    params: dict,
    data_version: str,
    operator: str,
    now: datetime | None = None,
) -> str:
    """新建一次运行，返回 run_id。同日多次调用按序号递增。"""
    if not data_version:
        raise ValueError("data_version 不能为空，需能定位数据集版本")
    if not operator:
        raise ValueError("operator 不能为空")

    ensure_schema(conn)
    moment = now or datetime.now()
    stamp = moment.strftime("%Y%m%d")
    prefix = f"RUN{stamp}-"

    row = conn.execute(
        "SELECT run_id FROM run WHERE run_id LIKE ? ORDER BY run_id DESC LIMIT 1",
        (prefix + "%",),
    ).fetchone()
    seq = 1 if row is None else int(row[0].rsplit("-", 1)[1]) + 1
    run_id = f"{prefix}{seq:02d}"

    conn.execute(
        "INSERT INTO run (run_id, year, params_json, data_version, operator, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            run_id,
            int(year),
            json.dumps(params, ensure_ascii=False, sort_keys=True),
            data_version,
            operator,
            moment.isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    return run_id


def get_run(conn: sqlite3.Connection, run_id: str) -> dict:
    """读取运行快照；params_json 已解析为 dict。不存在时抛 KeyError。"""
    row = conn.execute(
        "SELECT run_id, year, params_json, data_version, operator, created_at"
        " FROM run WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"运行不存在: {run_id}")
    return {
        "run_id": row[0],
        "year": row[1],
        "params": json.loads(row[2]),
        "data_version": row[3],
        "operator": row[4],
        "created_at": row[5],
    }


def list_runs(conn: sqlite3.Connection, year: int | None = None) -> list:
    """按创建时间列运行，供界面选择历史运行。"""
    sql = (
        "SELECT run_id, year, data_version, operator, created_at"
        " FROM run"
    )
    args: tuple = ()
    if year is not None:
        sql += " WHERE year = ?"
        args = (int(year),)
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, args).fetchall()
    return [
        {
            "run_id": r[0],
            "year": r[1],
            "data_version": r[2],
            "operator": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]
