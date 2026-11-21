# 部署说明

负责人：6 号　状态：第 1 阶段骨架；第 2 周随 2 号 `src/store.py` 补齐建库与装载命令，第 3 阶段定稿。

## 1 环境要求

- 操作系统：Windows 10/11、macOS 或 Linux。
- Python：3.11 及以上（`tomllib` 需要 3.11；开发环境为 3.12）。
- 数据库：SQLite，Python 标准库自带，无需单独安装。
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

## 3 数据库初始化

第 2 周补齐：2 号交付 `src/store.py` 后填写确切命令。建库顺序固定为
`db/schema.sql` → `db/schema_run.sql` → `db/schema_log.sql`，由 `src.store.init_db(path)` 一次执行，缺一项即报错。

默认数据库路径为 `data/sim.db`，可用环境变量 `SIM_DB` 覆盖。

## 4 启动

开发/演示（mock 假数据，不需要数据库）：

```powershell
# Windows PowerShell
$env:API_MOCK="1"; uvicorn src.api.main:app --reload --port 8000
```

```bash
# macOS / Linux / Git Bash
API_MOCK=1 uvicorn src.api.main:app --reload --port 8000
```

浏览器打开 `http://127.0.0.1:8000`。

真实模式（需先完成第 3 节建库与第 5 节数据装载）：

```bash
uvicorn src.api.main:app --reload --port 8000
```

未就绪的端点返回 501，页面会显示明确错误；真实模式不会回退到假数据。

## 5 演示数据装载

第 2 周补齐：

- 小数据集：`data/small/`，由 2 号生成并入库，供对账与演示。
- 15 万规模：`data/large/`，按 `config/rules.toml` 的 seed 重新生成，不入库。
- 生成命令以 2 号 `src/gen_data.py` 的 `generate(scale, out_dir, seed)` 为准。

## 6 已知限制

- mock 模式只用于第 1 阶段联调；演示成片必须使用真实模式。
- SQLite 单文件、单机演示，不做并发写入与公网部署，没有鉴权。
- 15 万数据与演示视频不入库，按文档重新生成或拷贝。
- 页面只读 4 号接口，不直连数据库；接口未就绪时只能看到 501 提示。
