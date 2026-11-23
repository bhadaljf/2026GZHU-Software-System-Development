# 投档引擎模块

负责人：3 号

## 当前状态

- 已搭建四批次投档、梯度分档、名额到校、结转和日志的完整代码框架。
- 已完成模块导入、语法检查与内存构造数据冒烟验证。
- **暂未在 2 号提供的正式小数据集上执行**：当前 `main` 尚无可用的
  `load_dataset()` 和 `data/small` 数据文件。待依赖合入后再做人工预期对账。

## 输入
- 只读数据集：`plan`、`quota_plan`、`self_recruit_eligibility`、`student`、`volunteer`
- 规则参数：`config/rules.toml`

## 输出
- `admit_result`：录取结果，字段见契约第 2 节
- `admit_log`：投档日志，原因码见契约第 4 节
- `run`：运行快照（由 1 号的 `src/run_meta.py` 写入）

## 约束
- 不修改表结构与接口字段；需要新字段先走契约变更。
- 不在引擎内重算计划切分，计划数以 `plan` 表为准。
- 结果可重复：同一 run 参数与数据版本重跑不叠加。
- 引擎不连接数据库；持久化统一交给 `store.write_results`。
