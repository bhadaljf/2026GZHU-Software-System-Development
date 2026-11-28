"""造一个 4 号本地自测用的演示库（不是小组正式库）。

为什么要它：2 号的 `src/store.py init_db` 与 3 号的引擎还没交付，`data/app.db` 不存在，
4 号模块会自动走 mock 假数据，看不到“真实库分支”的 SQL 到底跑不跑得通。

这个脚本用**与契约一致的临时小数据**建一个 `data/demo_4hao.db`：
- 只读它不会污染正式库，正式库仍由 2 号建（`data/app.db`）；
- 数据量很小（6 考生、7 计划、4 条录取），只用于验证 SQL 分支与口径，**不得用于对账或写报告**；
- 带上 `plan_summary` 汇总表，所以统计会走“读汇总表”这条第二阶段的路。

用法（仓库根目录）：
    python scripts/make_demo_db.py                          # 生成 data/demo_4hao.db
    python scripts/make_demo_db.py --out data/x.db           # 指定输出
    python scripts/make_demo_db.py --no-summary              # 不建汇总表，验证在线聚合回退

生成后这样验证真库分支：
    python -m src.query.selfcheck --db data/demo_4hao.db --run RUN-TEST-01 --mock 0
    python -m src.query.bench    --db data/demo_4hao.db --run RUN-TEST-01 --mock 0 --repeat 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "test"))  # 复用 4 号自测里的建库夹具，保证字段与测试完全一致

from test_query_module import RUN, build_db  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="造 4 号自测演示库")
    ap.add_argument("--out", default=str(ROOT / "data" / "demo_4hao.db"), help="输出路径")
    ap.add_argument("--no-summary", action="store_true", help="不建 plan_summary，验证回退在线聚合")
    args = ap.parse_args(argv)

    out = Path(args.out)
    if out.exists():
        out.unlink()
    out.parent.mkdir(parents=True, exist_ok=True)
    build_db(out, with_summary=not args.no_summary)

    print(f"已生成演示库：{out}")
    print(f"  run_id = {RUN}，年度 2026，6 名考生 / 7 个计划 / 4 条录取")
    print(f"  汇总表 plan_summary：{'未建（统计走在线聚合）' if args.no_summary else '已建（统计优先读它）'}")
    print("\n接着跑这两条（真库模式，不走假数据）：")
    print(f"  python -m src.query.selfcheck --db {out} --run {RUN} --mock 0")
    print(f"  python -m src.query.bench    --db {out} --run {RUN} --mock 0 --repeat 5")
    return 0


if __name__ == "__main__":
    sys.exit(main())
