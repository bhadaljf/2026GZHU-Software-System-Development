# 投档引擎模块

负责人：3 号

## 输入
- 只读数据集：`plan`、`quota_plan`、`self_recruit_eligibility`、`student`、`volunteer`
- 规则参数：`config/rules.yaml`

## 输出
- `admit_result`：录取结果，字段见契约第 2 节
- `admit_log`：投档日志，原因码见契约第 4 节
- `run`：运行快照（由 1 号的 `src/run_meta.py` 写入）

## 约束
- 不修改表结构与接口字段；需要新字段先走契约变更。
- 不在引擎内重算计划切分，计划数以 `plan` 表为准。
- 结果可重复：同一 run 参数与数据版本重跑不叠加。
