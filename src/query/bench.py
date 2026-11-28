"""三类查询响应时间记录（4 号：黎俊彤）。

对应第二阶段要求「记录三类查询的响应时间」（`docs/07_分工与计划.md` 4 号「性能」一条）。
本脚本只做测量与打表，不改任何业务口径；结果可直接贴进 `docs/05_测试报告.md` 或报告正文。

用法（仓库根目录）：
    python -m src.query.bench                                  # 库没建好就走 mock 数据
    python -m src.query.bench --db data/app.db --run RUN20261210-01
    python -m src.query.bench --repeat 5 --batch 3

出参：dict{run_id, mock, student_id, plan_id, batch, repeat, rows, missing_indexes}
"""

from __future__ import annotations

import argparse
import sys

try:
    from src.query import DB_PATH, connect, is_db_ready
    from src.query.perf import missing_indexes, timed
except ImportError:
    from query import DB_PATH, connect, is_db_ready
    from query.perf import missing_indexes, timed


def _first_id(conn, table: str, column: str, default: str) -> str:
    """取库里第一条编号作抽样对象；取不到就用默认值。"""
    try:
        row = conn.execute(f"SELECT {column} FROM {table} ORDER BY {column} LIMIT 1").fetchone()
        return row[column] if row else default
    except Exception:
        return default


def bench(db: str | None = None, run_id: str = "RUN-MOCK", student_id: str | None = None,
          plan_id: str | None = None, batch: int = 3, repeat: int = 3,
          mock: bool | None = None) -> dict:
    """跑三类查询各 repeat 次，返回每次与平均/最大耗时（毫秒）。"""
    from src.query.plan import get_plan_admissions
    from src.query.stats import get_batch_stats
    from src.query.student import get_student_result

    use_mock_data = True if mock is None else bool(mock)
    if mock is None and is_db_ready(db):
        use_mock_data = False

    conn = None
    if not use_mock_data:
        conn = connect(db)
        student_id = student_id or _first_id(conn, "student", "student_id", "S01")
        plan_id = plan_id or _first_id(conn, "plan", "plan_id", "P-A3")
    else:
        student_id = student_id or "S01"
        plan_id = plan_id or "P-A3"

    kwargs = {"conn": conn, "mock": use_mock_data}
    jobs = [
        ("考生结果查询", lambda: get_student_result(run_id, student_id, **kwargs)),
        ("计划名单查询", lambda: get_plan_admissions(run_id, plan_id, page=1, size=100, **kwargs)),
        ("批次统计", lambda: get_batch_stats(run_id, int(batch), **kwargs)),
    ]

    rows = []
    for name, fn in jobs:
        times = []
        for _ in range(max(int(repeat), 1)):
            with timed() as box:
                fn()
            times.append(box["ms"])
        rows.append({
            "name": name,
            "avg_ms": round(sum(times) / len(times), 2),
            "max_ms": max(times),
            "runs": times,
        })

    result = {
        "run_id": run_id,
        "mock": use_mock_data,
        "student_id": student_id,
        "plan_id": plan_id,
        "batch": int(batch),
        "repeat": max(int(repeat), 1),
        "rows": rows,
        "index_checked": conn is not None,
        "missing_indexes": missing_indexes(conn) if conn else [],
    }
    if conn is not None:
        conn.close()
    return result


def print_table(result: dict) -> None:
    """按 Markdown 表格打印，方便直接贴进文档/报告。"""
    print(f"\n运行编号：`{result['run_id']}`　数据：{'mock（假数据）' if result['mock'] else '真实库'}"
          f"　抽样：{result['student_id']} / {result['plan_id']} / 第 {result['batch']} 批"
          f"　次数：{result['repeat']}\n")
    print("| 查询 | 平均（ms） | 最大（ms） | 各次（ms） |")
    print("| --- | --- | --- | --- |")
    for r in result["rows"]:
        print(f"| {r['name']} | {r['avg_ms']} | {r['max_ms']} | "
              f"{'、'.join(str(t) for t in r['runs'])} |")
    if not result.get("index_checked"):
        print("\n（mock 模式不读库，未检查索引；接真库后加 `--mock 0` 再跑一次。）")
    elif result["missing_indexes"]:
        print(f"\n未建的建议索引（{len(result['missing_indexes'])} 个，交 2 号）：")
        for name in result["missing_indexes"]:
            print(f"- {name}")
    else:
        print("\n建议索引齐全。")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="4 号查询响应时间记录")
    ap.add_argument("--db", default=None, help=f"数据库路径，默认 {DB_PATH}")
    ap.add_argument("--run", default="RUN-MOCK", help="运行编号")
    ap.add_argument("--student", default=None, help="抽样考生编号，默认取库里第一条")
    ap.add_argument("--plan", default=None, help="抽样计划编号，默认取库里第一条")
    ap.add_argument("--batch", type=int, default=3, help="抽样批次，默认 3")
    ap.add_argument("--repeat", type=int, default=3, help="每类查询重复次数，默认 3")
    ap.add_argument("--mock", choices=["auto", "1", "0"], default="auto",
                    help="auto=库可用就用真库；1=强制 mock；0=强制真库")
    args = ap.parse_args(argv)

    mock = None if args.mock == "auto" else (args.mock == "1")
    if mock is False and not is_db_ready(args.db):
        print(f"✗ 库未就绪：{args.db or DB_PATH}，请改用 --mock 1")
        return 2
    print_table(bench(db=args.db, run_id=args.run, student_id=args.student,
                      plan_id=args.plan, batch=args.batch, repeat=args.repeat, mock=mock))
    return 0


if __name__ == "__main__":
    sys.exit(main())
