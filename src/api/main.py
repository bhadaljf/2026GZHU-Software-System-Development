"""接口网关（6 号）。

职责：FastAPI 应用，只做参数校验与转发，不写投档逻辑，也不直连业务表。
端点与入参见 docs/09_接口清单.md 第 3 节；返回结构以 4 号 docs/04 为准。

模式：
- 默认真实模式：调用 4 号查询层并强制 ``mock=False``；库/模块未就绪返回 501/503，
  不静默回退假数据；
- ``API_MOCK=1``：返回 src/api/mocks.py 的假数据，供页面独立演示（含案例对比）。
"""

from __future__ import annotations

import os
import sqlite3
from importlib import import_module
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.api import mocks

BASE = Path(__file__).resolve().parents[2]
INTERFACE = BASE / "interface"
DB_PATH = Path(os.getenv("SIM_DB") or os.getenv("ZKS_DB") or (BASE / "data" / "app.db"))
OPERATOR = os.getenv("SIM_OPERATOR", "6号")

# 4 号查询层默认读 ZKS_DB；让两边始终指向同一个库（SIM_DB 优先级更高）。
os.environ["ZKS_DB"] = str(DB_PATH)

# 真实模式下由 /execute 写入、/progress 读取；mock 模式不使用。
_PROGRESS: dict[str, dict] = {}

app = FastAPI(title="广州中考录取模拟")
app.mount("/css", StaticFiles(directory=INTERFACE / "css"), name="css")
app.mount("/js", StaticFiles(directory=INTERFACE / "js"), name="js")


class RunRequest(BaseModel):
    year: int = 2026
    scale: str = "small"
    params: Optional[dict] = None


class ExecuteRequest(BaseModel):
    batches: list[int] = Field(default_factory=lambda: [1, 2, 3, 4])


def _need(module: str, name: str):
    """延迟导入真实模块；未就绪时返回 501，绝不回退 mock。"""
    try:
        mod = import_module(module)
    except ImportError as exc:
        raise HTTPException(status_code=501, detail=f"依赖未就绪: {module}") from exc
    fn = getattr(mod, name, None)
    if fn is None:
        raise HTTPException(status_code=501, detail=f"依赖未就绪: {module}.{name}")
    return fn


def _query(module: str, name: str, *args, **kwargs):
    """调用 4 号查询函数：强制 mock=False，并把库错误转成 503。"""
    fn = _need(module, name)
    try:
        return fn(*args, mock=False, **kwargs)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"数据库未就绪: {exc}") from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail=f"数据库查询失败: {exc}") from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=f"依赖未实现: {module}.{name}") from exc


def _ensure_sql(conn: sqlite3.Connection, path: Path) -> None:
    """补齐 2 号 init_db 未执行的 DDL（run/log）。DDL 均为 IF NOT EXISTS。"""
    if path.exists():
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.commit()


def _check_batch(batch: int) -> int:
    if batch not in (1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="批次必须是 1—4")
    return batch


def _check_batches(batches: list[int]) -> list[int]:
    if not batches:
        raise HTTPException(status_code=400, detail="batches 不能为空")
    bad = [b for b in batches if b not in (1, 2, 3, 4)]
    if bad:
        raise HTTPException(status_code=400, detail=f"批次必须是 1—4: {bad}")
    return sorted(set(batches))


def _balances(run_id: str, batches: list[int]) -> list[dict]:
    """执行后用 4 号批次统计组装进度余额；失败时不影响主流程。"""
    try:
        fn = _need("src.query.stats", "get_batch_stats")
        out = []
        for batch in batches:
            stats = fn(run_id, batch, mock=False)
            out.append({
                "batch": batch,
                "quota": stats.get("quota_total"),
                "admitted": stats.get("admitted_count"),
                "remaining": stats.get("remaining_quota"),
            })
        return out
    except Exception:
        return []


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INTERFACE / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "mode": "mock" if mocks.MOCK else "real"}


@app.post("/api/runs")
def create_run(req: RunRequest) -> dict:
    if req.scale not in ("small", "large"):
        raise HTTPException(status_code=400, detail="scale 只能是 small 或 large")

    if mocks.MOCK:
        return mocks.create_run(req.year, req.scale)

    init_db = _need("src.store", "init_db")
    connect = _need("src.store", "connect")
    ensure_run = _need("src.run_meta", "ensure_schema")
    create = _need("src.run_meta", "create_run")
    load_rules = _need("src.config", "load_rules")

    rules = req.params or load_rules()
    seed = (rules.get("data") or {}).get("seed")
    data_version = f"{req.scale}-v1" + (f"-seed{seed}" if seed is not None else "")

    if not DB_PATH.exists():
        init_db(str(DB_PATH), str(BASE / "db" / "schema.sql"))
    conn = connect(str(DB_PATH))
    try:
        ensure_run(conn)
        _ensure_sql(conn, BASE / "db" / "schema_log.sql")
        run_id = create(conn, req.year, rules, data_version, OPERATOR)
    finally:
        conn.close()
    return {"run_id": run_id}


@app.post("/api/runs/{run_id}/execute")
def execute(run_id: str, req: ExecuteRequest) -> dict:
    batches = _check_batches(req.batches)

    if mocks.MOCK:
        return mocks.execute(run_id, batches)

    connect = _need("src.store", "connect")
    get_run = _need("src.run_meta", "get_run")
    load_dataset = _need("src.gen_data", "load_dataset")
    load_rules = _need("src.config", "load_rules")
    run_batches = _need("src.engine.runner", "run_batches")
    write_results = _need("src.store", "write_results")

    conn = connect(str(DB_PATH))
    try:
        try:
            run = get_run(conn, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"运行不存在: {run_id}") from exc

        scale = "large" if str(run.get("data_version", "")).startswith("large") else "small"
        try:
            dataset = load_dataset(str(BASE / "data" / scale))
        except NotImplementedError as exc:
            raise HTTPException(
                status_code=501,
                detail="2 号 load_dataset 尚未实现（等 2 号 W2 合入）",
            ) from exc
        rules = load_rules()

        _PROGRESS[run_id] = {"stage": "running", "done": 0, "total": len(batches), "balances": []}
        try:
            out = run_batches(dataset, rules, run_id, batches)
            try:
                # 2 号 W2 的签名是 write_results(conn, run_out)
                write_results(conn, out)
            except TypeError:
                # docs/09 首版签名兜底
                write_results(run_id, out.results, out.logs)
        except NotImplementedError as exc:
            _PROGRESS[run_id] = {
                "stage": "error", "done": 0, "total": len(batches),
                "balances": [], "detail": str(exc),
            }
            raise HTTPException(status_code=501, detail=f"投档结果写入未实现: {exc}") from exc
        except Exception as exc:
            _PROGRESS[run_id] = {
                "stage": "error", "done": 0, "total": len(batches),
                "balances": [], "detail": str(exc),
            }
            raise
    finally:
        conn.close()

    progress = {
        "stage": "done",
        "done": len(batches),
        "total": len(batches),
        "balances": _balances(run_id, batches),
    }
    _PROGRESS[run_id] = progress
    return {"run_id": run_id, "progress": progress}


@app.get("/api/runs/{run_id}/progress")
def progress(run_id: str) -> dict:
    if mocks.MOCK:
        return mocks.progress(run_id)
    return _PROGRESS.get(
        run_id,
        {"stage": "idle", "done": 0, "total": 0, "balances": []},
    )


@app.get("/api/students/{sid}/result")
def student_result(sid: str, run_id: str = Query(..., description="运行编号")) -> dict:
    if mocks.MOCK:
        data = mocks.student_result(sid, run_id)
    else:
        data = _query("src.query.student", "get_student_result", run_id, sid)
    if not data.get("exists", True):
        raise HTTPException(status_code=404, detail=f"考生不存在或该运行无结果: {sid}")
    return data


@app.get("/api/plans/{pid}/admissions")
def plan_admissions(
    pid: str,
    run_id: str = Query(..., description="运行编号"),
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=500),
) -> dict:
    if mocks.MOCK:
        data = mocks.plan_admissions(pid, run_id, page, size)
    else:
        data = _query(
            "src.query.plan", "get_plan_admissions",
            run_id, pid, page=page, size=size,
        )
    if not data.get("exists", True):
        raise HTTPException(status_code=404, detail=f"计划不存在: {pid}")
    return data


@app.get("/api/stats/batch/{batch}")
def batch_stats(batch: int, run_id: str = Query(..., description="运行编号")) -> dict:
    _check_batch(batch)
    if mocks.MOCK:
        return mocks.batch_stats(batch, run_id)
    return _query("src.query.stats", "get_batch_stats", run_id, batch)


@app.get("/api/stats/school/{sid}")
def school_stats(sid: str, run_id: str = Query(..., description="运行编号")) -> dict:
    if mocks.MOCK:
        data = mocks.school_stats(sid, run_id)
    else:
        data = _query("src.query.stats", "get_school_stats", run_id, sid)
    if not data.get("exists", True):
        raise HTTPException(status_code=404, detail=f"学校不存在: {sid}")
    return data


@app.get("/api/distribution/{batch}")
def distribution(batch: int, run_id: str = Query(..., description="运行编号")) -> dict:
    _check_batch(batch)
    if mocks.MOCK:
        return mocks.distribution(batch, run_id)
    return _query("src.query.stats", "get_score_distribution", run_id, batch)


@app.get("/api/reasons")
def reasons() -> list[dict]:
    if mocks.MOCK:
        return mocks.reasons()
    return _need("src.query.reasons", "all_reasons")()


def _export_response(fn, run_id: str, prefix: str):
    out_dir = BASE / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{prefix}_{run_id}.csv"
    try:
        path = fn(run_id, str(out_path), mock=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"数据库未就绪: {exc}") from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail=f"数据库查询失败: {exc}") from exc
    return FileResponse(Path(path), media_type="text/csv", filename=Path(path).name)


@app.get("/api/export/admissions.csv")
def export_admissions(run_id: str = Query(..., description="运行编号")):
    if mocks.MOCK:
        return Response(
            content=mocks.admissions_csv(run_id),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="admit_{run_id}.csv"'},
        )
    return _export_response(
        _need("src.export.export_csv", "export_admissions"), run_id, "admit",
    )


@app.get("/api/export/stats.csv")
def export_stats(run_id: str = Query(..., description="运行编号")):
    if mocks.MOCK:
        return Response(
            content=mocks.stats_csv(run_id),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="stats_{run_id}.csv"'},
        )
    return _export_response(
        _need("src.export.export_csv", "export_stats"), run_id, "stats",
    )


print(f"[api] 模式：{'mock（假数据）' if mocks.MOCK else 'real（真实模块）'}")
