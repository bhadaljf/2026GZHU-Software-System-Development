"""接口网关（6 号）。

职责：FastAPI 应用，只做参数校验与转发，不写投档逻辑，也不直连数据库。
端点与入参见 docs/09_接口清单.md 第 3 节；返回结构见 docs/08 第 6 节。

模式：
- 默认真实模式：延迟导入 3 号/4 号模块，未就绪时返回 501，不静默回退假数据；
- ``API_MOCK=1``：返回 src/api/mocks.py 的假数据，供页面独立联调（T-06）。
"""

from __future__ import annotations

import os
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
DB_PATH = Path(os.getenv("SIM_DB") or (BASE / "data" / "sim.db"))
OPERATOR = os.getenv("SIM_OPERATOR", "6号")

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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INTERFACE / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/runs")
def create_run(req: RunRequest) -> dict:
    if req.scale not in ("small", "large"):
        raise HTTPException(status_code=400, detail="scale 只能是 small 或 large")

    if mocks.MOCK:
        return mocks.create_run(req.year, req.scale)

    init_db = _need("src.store", "init_db")
    connect = _need("src.store", "connect")
    create = _need("src.run_meta", "create_run")
    load_rules = _need("src.config", "load_rules")

    rules = req.params or load_rules()
    seed = (rules.get("data") or {}).get("seed")
    data_version = f"{req.scale}-v1" + (f"-seed{seed}" if seed is not None else "")

    if not DB_PATH.exists():
        init_db(str(DB_PATH))
    conn = connect(str(DB_PATH))
    try:
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
        run = get_run(conn, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"运行不存在: {run_id}") from exc
    finally:
        conn.close()

    scale = "large" if str(run.get("data_version", "")).startswith("large") else "small"
    dataset = load_dataset(str(BASE / "data" / scale))
    rules = load_rules()

    _PROGRESS[run_id] = {
        "stage": "running",
        "done": 0,
        "total": len(batches),
        "balances": [],
    }
    try:
        out = run_batches(dataset, rules, run_id, batches)
        write_results(run_id, out.results, out.logs)
    except Exception as exc:  # 引擎异常要让页面看到，而不是伪装成完成
        _PROGRESS[run_id] = {
            "stage": "error",
            "done": 0,
            "total": len(batches),
            "balances": [],
            "detail": str(exc),
        }
        raise

    progress = {
        "stage": "done",
        "done": len(batches),
        "total": len(batches),
        "balances": [],
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
        try:
            return mocks.student_result(sid, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"考生不存在: {sid}") from exc

    get_result = _need("src.query.student", "get_student_result")
    try:
        return get_result(run_id, sid)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"考生不存在或该运行无结果: {sid}") from exc


@app.get("/api/plans/{pid}/admissions")
def plan_admissions(
    pid: str,
    run_id: str = Query(..., description="运行编号"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
) -> dict:
    if mocks.MOCK:
        try:
            return mocks.plan_admissions(pid, run_id, page, size)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"计划不存在: {pid}") from exc

    get_admissions = _need("src.query.plan", "get_plan_admissions")
    try:
        return get_admissions(run_id, pid, page=page, size=size)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"计划不存在: {pid}") from exc


@app.get("/api/stats/batch/{batch}")
def batch_stats(batch: int, run_id: str = Query(..., description="运行编号")) -> dict:
    _check_batch(batch)
    if mocks.MOCK:
        return mocks.batch_stats(batch, run_id)
    get_stats = _need("src.query.stats", "get_batch_stats")
    return get_stats(run_id, batch)


@app.get("/api/stats/school/{sid}")
def school_stats(sid: str, run_id: str = Query(..., description="运行编号")) -> dict:
    if mocks.MOCK:
        try:
            return mocks.school_stats(sid, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"学校不存在: {sid}") from exc
    get_stats = _need("src.query.stats", "get_school_stats")
    try:
        return get_stats(run_id, sid)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"学校不存在: {sid}") from exc


@app.get("/api/distribution/{batch}")
def distribution(batch: int, run_id: str = Query(..., description="运行编号")) -> dict:
    _check_batch(batch)
    if mocks.MOCK:
        return mocks.distribution(batch, run_id)
    get_distribution = _need("src.query.stats", "get_score_distribution")
    return get_distribution(run_id, batch)


@app.get("/api/reasons")
def reasons() -> list[dict]:
    if mocks.MOCK:
        return mocks.reasons()
    return _need("src.query.reasons", "all_reasons")()


@app.get("/api/export/admissions.csv")
def export_admissions(run_id: str = Query(..., description="运行编号")):
    if mocks.MOCK:
        return Response(
            content=mocks.admissions_csv(run_id),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="admit_{run_id}.csv"',
            },
        )

    export = _need("src.export.export_csv", "export_admissions")
    out_dir = BASE / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"admit_{run_id}.csv"
    path = export(run_id, str(out_path))
    return FileResponse(
        Path(path),
        media_type="text/csv",
        filename=Path(path).name,
    )


print(f"[api] 模式：{'mock（假数据）' if mocks.MOCK else 'real（真实模块）'}")
