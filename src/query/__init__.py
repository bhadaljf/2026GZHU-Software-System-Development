"""查询与统计包（4 号：黎俊彤）。

职责边界（见 docs/09_接口清单.md 第 3 节）：
- 只读 SQLite 中的主数据表、plan 表与结果/日志表（admit_result / admit_log / carry_log），
  不实现任何投档、分档、名额结转规则——那些属于 3 号；
- 对外只返回 dict / str（CSV 路径），HTTP 路由由 6 号在 src/api/main.py 里挂；
- 首版若真实数据库还没建好（2 号、3 号未交付），自动进入 mock 模式，
  返回与 docs/08_协作规范与样例.md 第 6 节同形的假数据，供 6 号先做页面。

负责人：4 号
入参：见各模块函数
出参：dict（字段以 docs/00_契约.md 为准）
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
from pathlib import Path

# 仓库根目录：src/query/__init__.py -> parents[2]
BASE_DIR = Path(__file__).resolve().parents[2]
# 数据库路径：默认 data/app.db，可用环境变量 ZKS_DB 覆盖
DB_PATH = Path(os.environ["ZKS_DB"]) if os.environ.get("ZKS_DB") else (BASE_DIR / "data" / "app.db")
# 导出目录
EXPORT_DIR = BASE_DIR / "export"

# 判断“库已可用”至少要有的表；缺一张就说明 2 号/3 号还没交付
REQUIRED_TABLES = ("student", "plan", "admit_result", "admit_log", "volunteer")


def connect(path=None, read_only: bool = True) -> sqlite3.Connection:
    """打开数据库连接。4 号只读，默认用只读 URI 打开，写操作会直接报错。

    参数：
        path      数据库路径，默认 DB_PATH
        read_only 是否只读打开
    返回：sqlite3.Connection（row_factory=sqlite3.Row，可按列名取值）
    """
    p = Path(path or DB_PATH)
    if not p.exists():
        raise FileNotFoundError(f"数据库不存在：{p}（先用 src/store.py 建库并写入结果）")
    if read_only:
        conn = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    return conn


def is_db_ready(path=None) -> bool:
    """库文件存在且关键表齐全，才算“可查真实数据”。"""
    p = Path(path or DB_PATH)
    if not p.exists():
        return False
    try:
        conn = connect(p)
    except (sqlite3.Error, FileNotFoundError):
        return False
    try:
        cur = conn.cursor()
        found = {row[0] for row in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        return all(t in found for t in REQUIRED_TABLES)
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def use_mock(mock=None) -> bool:
    """是否走 mock 假数据。

    优先级：显式入参 mock > 环境变量 ZKS_MOCK > 库是否可用（不可用就 mock）。
    """
    if mock is not None:
        return bool(mock)
    env = os.environ.get("ZKS_MOCK", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    return not is_db_ready()


@contextlib.contextmanager
def open_cursor(conn: sqlite3.Connection | None = None, path=None):
    """借用调用方的连接，或者自己开一个只读连接并在退出时关掉。"""
    owned = conn is None
    if owned:
        conn = connect(path)
    try:
        yield conn.cursor()
    finally:
        if owned:
            conn.close()
