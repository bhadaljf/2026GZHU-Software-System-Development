-- seed_small.sql 【2号维护】人工基准小数据集
-- 用途：预测试、人工推演对账，严禁gen_data工具导出反填本文件
-- 规模：2所初中、4所公办高中、16名考生；符合任务书小数据测试样例要求
-- 依赖：必须先执行 db/schema.sql 建表之后，再执行本SQL

-- 1. 插入初中 middle_school
INSERT INTO middle_school (school_id, name, district) VALUES
('M01', '初中A', 'A区'),
('M02', '初中B', 'B区');

-- 2. 插入高中 high_school，recruit_batch 只能3/4，契约约束
INSERT INTO high_school (school_id, name, type, recruit_batch) VALUES
('H01', '示范高中1', 'demo', 3),
('H02', '示范高中2', 'demo', 3),
('H03', '普高3', 'normal', 4),
('H04', '普高4', 'normal', 4);

-- 3. 插入考生 student，R39：(score, tie_seq)全局唯一
INSERT INTO student (student_id, name, junior_school_id, score, tie_seq) VALUES
('S00','考生00','M01',710,1),
('S01','考生01','M02',680,2),
('S02','考生02','M01',655,3),
('S03','考生03','M02',620,4),
('S04','考生04','M01',590,5),
('S05','考生05','M02',560,6),
('S06','考生06','M01',530,7),
('S07','考生07','M02',510,8),
('S08','考生08','M01',690,9),
('S09','考生09','M02',665,10),
('S10','考生10','M01',630,11),
('S11','考生11','M02',600,12),
('S12','考生12','M01',575,13),
('S13','考生13','M02',545,14),
('S14','考生14','M01',520,15),
('S15','考生15','M02',480,16);

-- 4. 招生计划 plan；R5计划切分；remaining初始等于quota；control_line >=492
INSERT INTO plan (plan_id, year, high_school_id, batch, category, quota, control_line, remaining) VALUES
('P01',2026,'H01',1,'self_recruit',4,500,4),
('P02',2026,'H01',2,'quota',10,492,10),
('P03',2026,'H01',3,'unified',16,492,16),
('P04',2026,'H02',1,'self_recruit',2,520,2),
('P05',2026,'H02',2,'quota',8,492,8),
('P06',2026,'H02',3,'unified',12,492,12),
('P07',2026,'H03',4,'unified',20,492,20),
('P08',2026,'H04',4,'unified',18,492,18);

-- 5. 名额分配子计划 quota_plan（R22 指标到校，batch=2计划）
INSERT INTO quota_plan (plan_id, junior_school_id, quota) VALUES
('P02','M01',6),
('P02','M02',4),
('P05','M01',5),
('P05','M02',3);

-- 6. 自主招生资格 self_recruit_eligibility；R21：同一高中rank唯一，status=ok有效
INSERT INTO self_recruit_eligibility (student_id, high_school_id, status, rank) VALUES
('S00','H01','ok',1),
('S01','H01','ok',2),
('S08','H02','ok',1),
('S09','H02','ok',2);

-- 7. 志愿 volunteer；R7志愿上限；(year,student_id,batch,seq)唯一；只录入部分典型志愿用于人工推演
INSERT INTO volunteer (year, student_id, batch, seq, plan_id) VALUES
(2026,'S00',1,1,'P01'),
(2026,'S01',1,1,'P01'),
(2026,'S08',1,1,'P04'),
(2026,'S09',1,1,'P04'),
(2026,'S00',3,1,'P03'),
(2026,'S01',3,1,'P03'),
(2026,'S08',3,1,'P06'),
(2026,'S09',3,1,'P06');
