-- 结果、投档日志与结转流水，3 号维护。
-- 建库顺序：schema.sql -> schema_run.sql -> schema_log.sql。

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS admit_result (
    result_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run(run_id),
    student_id TEXT NOT NULL REFERENCES student(student_id),
    plan_id TEXT NOT NULL REFERENCES plan(plan_id),
    batch INTEGER NOT NULL CHECK (batch IN (1, 2, 3, 4)),
    score INTEGER NOT NULL,
    tie_seq INTEGER NOT NULL,
    volunteer_no INTEGER NOT NULL CHECK (volunteer_no > 0),
    admit_order INTEGER NOT NULL CHECK (admit_order > 0),
    UNIQUE (run_id, student_id),
    UNIQUE (run_id, plan_id, admit_order)
);

CREATE INDEX IF NOT EXISTS idx_admit_result_run_plan
    ON admit_result (run_id, plan_id, admit_order);
CREATE INDEX IF NOT EXISTS idx_admit_result_run_batch
    ON admit_result (run_id, batch);

CREATE TABLE IF NOT EXISTS admit_log (
    log_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run(run_id),
    batch INTEGER NOT NULL CHECK (batch IN (1, 2, 3, 4)),
    band INTEGER NOT NULL CHECK (band >= 0),
    volunteer_no INTEGER,
    plan_id TEXT REFERENCES plan(plan_id),
    student_id TEXT REFERENCES student(student_id),
    action TEXT NOT NULL CHECK (action IN ('admit', 'skip')),
    reason_code TEXT CHECK (
        reason_code IS NULL OR reason_code IN
        ('R01', 'R02', 'R03', 'R04', 'R05', 'R06', 'R07')
    ),
    balance_before INTEGER,
    balance_after INTEGER,
    note TEXT,
    CHECK (
        (action = 'admit' AND reason_code IS NULL) OR
        (action = 'skip' AND reason_code IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_admit_log_run_student
    ON admit_log (run_id, student_id, batch, volunteer_no);
CREATE INDEX IF NOT EXISTS idx_admit_log_run_plan_reason
    ON admit_log (run_id, plan_id, reason_code);

CREATE TABLE IF NOT EXISTS carry_log (
    carry_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run(run_id),
    from_batch INTEGER NOT NULL CHECK (from_batch IN (1, 2)),
    to_plan_id TEXT NOT NULL REFERENCES plan(plan_id),
    high_school_id TEXT NOT NULL REFERENCES high_school(school_id),
    amount INTEGER NOT NULL CHECK (amount > 0),
    source_note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, from_batch, to_plan_id)
);

CREATE INDEX IF NOT EXISTS idx_carry_log_run_target
    ON carry_log (run_id, to_plan_id);
