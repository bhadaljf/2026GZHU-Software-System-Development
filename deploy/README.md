# 部署说明

负责人：6 号　状态：第二阶段联调版（2026-11-26）
适用：Windows / macOS / Linux，单机演示。

## 1 环境要求

- Python 3.11 及以上（`tomllib` 需要 3.11；开发环境为 3.12）。
- 依赖：`fastapi`、`uvicorn`（测试另需 `pytest`）。
- 数据库：SQLite，Python 标准库自带。
- 浏览器：Chrome / Edge 最新版。

## 2 依赖安装

```bash
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install fastapi uvicorn
pip install pytest        # 运行 test/auto 时需要
```

## 3 启动

### 3.1 mock 模式（无数据库，页面完整演示）

```powershell
# Windows PowerShell
$env:API_MOCK="1"; python -m uvicorn src.api.main:app --reload --port 8000
```

```bash
# Git Bash / macOS / Linux
API_MOCK=1 python -m uvicorn src.api.main:app --reload --port 8000
```

浏览器打开 `http://127.0.0.1:8000`。mock 固定运行编号 `RUN20261121-01` / `RUN20261121-02`，案例对比页直接用这两个。

### 3.2 真实模式

```bash
python -m uvicorn src.api.main:app --reload --port 8000
```

- 数据库默认 `data/app.db`；可用 `SIM_DB` 或 `ZKS_DB` 指定其他路径（网关会让 4 号查询层指向同一个库）。
- 数据库不存在时，“新建运行”会建库：`db/schema.sql`（主表）→ `db/schema_run.sql`（run）→ `db/schema_log.sql`（结果/日志/结转）。2 号 `store.init_db` 目前只执行主表，网关在 `src/api/main.py` 中补执行后两份 DDL；2 号修正 `init_db` 后可去掉这段兼容代码。
- 真实模式不回退假数据：库未就绪返回 503，模块未就绪返回 501。
- 当前 `/execute` 仍依赖 2 号 `load_dataset` 与 `write_results`：dev 上 `write_results` 还是 `NotImplementedError`，执行会返回 `501 依赖未就绪: src.store.write_results`。完整投档等 2 号 W2/3 号合入后再联调。

## 4 数据装载

目标：把 2 号 `Dataset` 写进 `data/app.db`，供 4 号查询。

- 小数据集：2 号 `src.gen_data.generate("small", out_dir, seed)` 返回 `Dataset`，再 `src.store.write_dataset(conn, dataset)` 入库；`src.gen_data.save_dataset` / `load_dataset` 支持 `data/small/dataset.json` 序列化。
- 15 万数据：2 号 `feature/2-data-large` 分支已实现 large 生成与 `load_dataset`，尚未合入 dev；合入后按 `config/rules.toml` 的 seed 重生成，不写入 Git。
- 当前 dev 的 small 生成/入库可用 2 号 `test_w2.py` 验证（写入 `./test.db`）；`data/app.db` 的正式装载命令待 2 号提供后补到本节。

## 5 导出

- 录取明细：`export/admit_{run_id}.csv`；
- 统计汇总：`export/stats_{run_id}.csv`；
- 4 号同时生成同名 `*_口径说明.md`，写明 run_id、列含义、空值规则。
- 编码 UTF-8 with BOM，Excel 直接打开不乱码；空值写“无”，不写 0。

## 6 已实现的接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | `{ok, mode}` |
| POST | `/api/runs` | 新建运行；真实模式首次建库 |
| POST | `/api/runs/{run_id}/execute` | 执行批次；当前真实模式 501（写入未实现） |
| GET | `/api/runs/{run_id}/progress` | 进度与余额 |
| GET | `/api/students/{sid}/result` | 考生结果；`exists:false` → 404 |
| GET | `/api/plans/{pid}/admissions` | 计划名单；分页 |
| GET | `/api/stats/batch/{batch}` | 批次统计 + `plans[]` |
| GET | `/api/stats/school/{sid}` | 学校总体/分批/分类/计划 |
| GET | `/api/distribution/{batch}` | 分数分布 + 参考线 |
| GET | `/api/reasons` | 原因码 |
| GET | `/api/export/admissions.csv` | 录取明细 CSV |
| GET | `/api/export/stats.csv` | 统计汇总 CSV（第二阶段新增，待契约登记） |

## 7 已知限制

- 真实投档写入 `write_results` 未实现，`/execute` 501；mock 模式可完整演示页面。
- 2 号 large 生成分支未合入 dev，15 万数据暂不能正式装载。
- 4 号统计当前在线聚合 `admit_result`，15 万数据下需测响应时间，必要时补汇总表/索引。
- 结转流水只有计划级 `carry_in/quota_total`，完整 `carry_log` 展示待补端点。
- 按初中 / 高中—批次查名单、基础数据管理界面、两例滑档案例仍需后续补齐（见 `docs/10`）。
- SQLite 单文件、单机演示，无鉴权、无并发写入。
- 15 万数据与演示视频不入库，按文档重新生成或拷贝。
