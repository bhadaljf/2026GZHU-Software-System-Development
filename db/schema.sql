-- 主数据与计划表结构，2 号维护
-- 字段以 docs/00_契约.md 为准。
--
-- 建库顺序（src/store.init_db 按此执行，缺一项即报错）：
--   1) db/schema.sql          主数据与计划表（2 号）
--   2) db/schema_run.sql      run 表（1 号，见 src/run_meta.ensure_schema）
--   3) db/schema_log.sql      结果、日志与结转流水（3 号）
--
-- 本文件只放主数据与计划：
--   middle_school / high_school / student / plan / quota_plan
--   self_recruit_eligibility / volunteer
-- run 表不在此处定义，避免两份 DDL 漂移。

-- db/schema.sql
-- W1 2号成员，主业务数据表定义
-- 依据：docs/00_契约.md v0.9；docs/01_需求与规则清单.md v1.0
-- ⚠注意：本文件不包含 run / admit_result / admit_log / carry_log
-- run表放在 db/schema_run.sql（1号维护）；日志表放在db/schema_log.sql（3号维护）

PRAGMA foreign_keys = ON; -- 开启SQLite外键约束检查

-- 初中表 middle_school
CREATE TABLE IF NOT EXISTS middle_school (
    school_id TEXT PRIMARY KEY, -- 初中唯一编号
    name TEXT NOT NULL, -- 学校名称
    district TEXT NOT NULL -- 所属行政区
);
CREATE UNIQUE INDEX idx_middle_name ON middle_school(name); -- 学校名称不可重复

-- 高中表 high_school
CREATE TABLE IF NOT EXISTS high_school (
    school_id TEXT PRIMARY KEY, -- 高中唯一编号
    name TEXT NOT NULL, -- 学校名称
    type TEXT NOT NULL, -- 学校类型（示范/普通）
    recruit_batch INTEGER NOT NULL CHECK(recruit_batch IN (3,4)) -- 统招接收批次，只能3/4 R6
);
CREATE UNIQUE INDEX idx_high_name ON high_school(name); -- 高中名称唯一

-- 考生表 student
CREATE TABLE IF NOT EXISTS student (
    student_id TEXT PRIMARY KEY, -- 考生编号
    name TEXT NOT NULL, -- 考生姓名
    junior_school_id TEXT NOT NULL REFERENCES middle_school(school_id), -- 所属初中外键 R23
    score INTEGER NOT NULL, -- 中考投档总分 R3
    tie_seq INTEGER NOT NULL -- 同分序号，越小优先级越高 R16/R39
);
CREATE UNIQUE INDEX idx_student_score_tieseq ON student(score, tie_seq); -- 同一总分tie_seq唯一 R39

-- 招生计划表 plan
CREATE TABLE IF NOT EXISTS plan (
    plan_id TEXT PRIMARY KEY, -- 计划唯一ID
    year INTEGER NOT NULL, -- 模拟年度
    high_school_id TEXT NOT NULL REFERENCES high_school(school_id), -- 归属高中外键
    batch INTEGER NOT NULL CHECK(batch IN (1,2,3,4)), -- 所属批次1‑4
    category TEXT NOT NULL CHECK(category IN ('self_recruit','quota','unified')), -- 计划类别：自招/名额分配/统招
    quota INTEGER NOT NULL CHECK(quota >= 0), -- 初始招生名额 R5
    control_line INTEGER NOT NULL CHECK(control_line >= 492), -- 投档控制线 ≥492 R10
    remaining INTEGER NOT NULL CHECK(remaining >= 0) -- 剩余名额，冗余字段 R29
);
CREATE UNIQUE INDEX idx_plan_uniq ON plan(year, high_school_id, batch, category); -- 联合唯一约束

-- 名额分配子计划 quota_plan（第二批专用）
CREATE TABLE IF NOT EXISTS quota_plan (
    plan_id TEXT NOT NULL REFERENCES plan(plan_id), -- 关联主计划ID
    junior_school_id TEXT NOT NULL REFERENCES middle_school(school_id), -- 关联初中ID
    quota INTEGER NOT NULL CHECK(quota >= 0), -- 分配到该初中的名额
    PRIMARY KEY(plan_id, junior_school_id) -- 复合主键 R22
);

-- 自主招生资格 self_recruit_eligibility
CREATE TABLE IF NOT EXISTS self_recruit_eligibility (
    student_id TEXT NOT NULL REFERENCES student(student_id), -- 考生ID外键
    high_school_id TEXT NOT NULL REFERENCES high_school(school_id), -- 高中ID外键
    status TEXT NOT NULL, -- 资格状态 ok/invalid
    rank INTEGER NOT NULL, -- 校内考核排名，越小优先级越高 R21
    PRIMARY KEY(student_id, high_school_id) -- 复合主键
);
CREATE UNIQUE INDEX idx_selfrecruit_high_rank ON self_recruit_eligibility(high_school_id, rank); -- 同高中rank唯一 R21

-- 志愿表 volunteer
CREATE TABLE IF NOT EXISTS volunteer (
    year INTEGER NOT NULL, -- 模拟年度
    student_id TEXT NOT NULL REFERENCES student(student_id), -- 考生外键
    batch INTEGER NOT NULL CHECK(batch IN (1,2,3,4)), -- 志愿所属批次
    seq INTEGER NOT NULL CHECK(seq > 0), -- 志愿序号，从1开始
    plan_id TEXT NOT NULL REFERENCES plan(plan_id), -- 报考计划外键
    PRIMARY KEY(year, student_id, batch, seq) -- 联合主键，防止同考生同批次重复序号 R7
);
