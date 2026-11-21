"""4 号自检脚本：不接页面、不接网关，直接验证查询统计的返回结构与口径。

用法（在仓库根目录执行）：
    python -m src.query.selfcheck               # 默认 mock 模式（库没建好时也能跑）
    python -m src.query.selfcheck --export      # 顺手生成 export/ 下的样例 CSV
    python -m src.query.selfcheck --db data/app.db --run RUN20261120-01   # 跑真实库

检查项：
1. 最低录取分与末位考生分别计算（P-A3 上分别应为 690 与 S02/710）；
2. 无人录取时 min_score 与 last_admitted 都是 None（P-G3），不得是 0；
3. 未录取考生能拿到 R01—R07 的原因码；
4. 分页参数边界（page/size 越界自动纠正）；
5. 统计完成率、余额守恒核对不出错。
"""

from __future__ import annotations

import argparse
import json
import sys

try:
    from src.query import DB_PATH, is_db_ready
except ImportError:
    from query import DB_PATH, is_db_ready


def _dump(title: str, obj) -> None:
    print(f"\n===== {title} =====")
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def run(db: str | None = None, run_id: str = "RUN-MOCK", export: bool = False,
        mock: bool | None = None) -> int:
    from src.query.plan import get_plan_admissions
    from src.query.reasons import all_reasons, describe
    from src.query.stats import get_batch_stats, get_score_distribution, get_school_stats
    from src.query.student import get_student_result
    from src.report.report import build_stats_report

    # --db 指定了库就自己开一个只读连接，所有查询复用，避免反复建连
    conn = None
    if db and mock is not True:
        from src.query import connect
        conn = connect(db)
    kwargs = {"mock": mock, "conn": conn}
    failures: list[str] = []

    # 1 考生查询
    for sid in ("S01", "S04", "S05", "S99"):
        r = get_student_result(run_id, sid, **kwargs)
        _dump(f"考生 {sid}", r)
        if sid == "S01" and not (r["admitted"] and r["plan_id"] == "P-A3"):
            failures.append(f"S01 应录取 P-A3，实际 {r['plan_id']}")
        if sid == "S05" and r["admitted"]:
            failures.append("S05 应未录取")
        if sid == "S99" and r["exists"]:
            failures.append("S99 不存在却返回 exists=True")

    # 2 计划名单（含“最低分 ≠ 末位考生”“无人录取”）
    for pid in ("P-A3", "P-G3", "P-XXXX"):
        r = get_plan_admissions(run_id, pid, page=1, size=100, **kwargs)
        _dump(f"计划 {pid}", r)
    r_a3 = get_plan_admissions(run_id, "P-A3", **kwargs)
    if r_a3["exists"]:
        if r_a3["min_score"] != 690:
            failures.append(f"P-A3 最低录取分应为 690，实际 {r_a3['min_score']}")
        if not r_a3["last_admitted"] or r_a3["last_admitted"]["student_id"] != "S02":
            failures.append("P-A3 末位考生应为 S02")
        if r_a3["min_score"] == (r_a3["last_admitted"] or {}).get("score"):
            failures.append("P-A3 最低分与末位考生分数相同，无法验证两个口径分开算")
    r_g3 = get_plan_admissions(run_id, "P-G3", **kwargs)
    if r_g3["exists"] and (r_g3["min_score"] is not None or r_g3["last_admitted"] is not None):
        failures.append("P-G3 无人录取，min_score 与 last_admitted 都应为 None（显示“无”）")

    # 3 分页边界
    r_edge = get_plan_admissions(run_id, "P-A3", page=0, size=0, **kwargs)
    if r_edge["page"] != 1 or r_edge["size"] < 1:
        failures.append(f"分页边界未纠正：page={r_edge['page']}, size={r_edge['size']}")
    _dump("分页边界 page=0&size=0", {"page": r_edge["page"], "size": r_edge["size"]})

    # 4 批次统计 / 学校统计 / 分数分布
    for b in (1, 2, 3, 4):
        _dump(f"第 {b} 批统计", get_batch_stats(run_id, b, **kwargs))
    for sid in ("H01", "H02", "H03", "H99"):
        _dump(f"学校 {sid} 统计", get_school_stats(run_id, sid, **kwargs))
    _dump("第 3 批分数分布", get_score_distribution(run_id, 3, **kwargs))

    # 5 原因码
    _dump("原因码", all_reasons())
    print("\nR01 ->", describe("R01"), "| R99 ->", describe("R99"))

    # 6 报表
    report = build_stats_report(run_id, **kwargs)
    _dump("统计报表（截取 overall/by_batch）",
          {"overall": report["overall"], "by_batch": report["by_batch"],
           "conservation": report["conservation"]})
    if report["conservation"]["mismatch"]:
        failures.append(f"余额守恒不一致 {report['conservation']['mismatch']} 个计划")

    # 7 导出样例
    if export:
        from src.export.export_csv import export_admissions, export_stats
        p1 = export_admissions(run_id, **kwargs)
        p2 = export_stats(run_id, **kwargs)
        print("\n导出的文件：")
        print(" -", p1)
        print(" -", p2)

    print("\n===== 自检结论 =====")
    if conn is not None:
        conn.close()
    if failures:
        for f in failures:
            print("✗", f)
        return 1
    print("✓ 全部通过")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="4 号查询统计自检")
    ap.add_argument("--db", default=None, help=f"数据库路径，默认 {DB_PATH}")
    ap.add_argument("--run", default="RUN-MOCK", help="运行编号")
    ap.add_argument("--export", action="store_true", help="同时生成 export/ 样例 CSV")
    ap.add_argument("--mock", choices=["auto", "1", "0"], default="auto",
                    help="auto=库可用就用真库；1=强制 mock；0=强制真库")
    args = ap.parse_args(argv)

    mock = None if args.mock == "auto" else (args.mock == "1")
    if mock is False and not is_db_ready(args.db):
        print(f"✗ 库未就绪：{args.db or DB_PATH}（缺表或文件不存在），请改用 --mock 1 或先建库")
        return 2
    return run(db=args.db, run_id=args.run, export=args.export, mock=mock)


if __name__ == "__main__":
    sys.exit(main())
