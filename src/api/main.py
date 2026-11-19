"""接口网关（6 号）。

FastAPI 应用：只做参数校验与转发，不写投档逻辑。
端点与入参见 docs/09_接口清单.md 第 3 节；业务函数由 3 号、4 号提供。
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).resolve().parents[2]
INTERFACE = BASE / "interface"

app = FastAPI(title="广州中考录取模拟")
app.mount("/css", StaticFiles(directory=INTERFACE / "css"), name="css")
app.mount("/js", StaticFiles(directory=INTERFACE / "js"), name="js")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INTERFACE / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


# TODO(6 号)：以下端点在本阶段接入 4 号与 3 号函数，返回结构与 09 一致
# POST /api/runs                     -> run_meta.create_run
# POST /api/runs/{run_id}/execute    -> engine.runner.run_batches
# GET  /api/runs/{run_id}/progress   -> 运行状态与各批余额
# GET  /api/students/{sid}/result    -> query.student.get_student_result
# GET  /api/plans/{pid}/admissions   -> query.plan.get_plan_admissions
# GET  /api/stats/batch/{batch}      -> query.stats.get_batch_stats
# GET  /api/stats/school/{sid}       -> query.stats.get_school_stats
# GET  /api/distribution/{batch}     -> query.stats.get_score_distribution
# GET  /api/reasons                  -> query.reasons.all_reasons
# GET  /api/export/admissions.csv    -> export.export_csv.export_admissions
