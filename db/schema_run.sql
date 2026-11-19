-- run 表（运行快照元数据），1 号维护
-- 契约字段见 docs/00_契约.md 第 2.2 节；由 src/run_meta.py 读写。

CREATE TABLE IF NOT EXISTS run (
    run_id       TEXT PRIMARY KEY,
    year         INTEGER NOT NULL,
    params_json  TEXT NOT NULL,
    data_version TEXT NOT NULL,
    operator     TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_run_year ON run (year, created_at);
