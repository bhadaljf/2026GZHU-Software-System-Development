# src/store.py W1+W2
# W1 2号成员；sqlite连接、初始化、批量写入
# W2新增：入库前调用validate校验、统计导入耗时、注释说明索引，write_results占位
import sqlite3  # 导入sqlite驱动
import os  # 导入文件系统操作
import time  # W2新增：统计导入耗时
from typing import List
from src.types import Dataset, Issue, RunOutput  # 导入自定义类型，W2增加RunOutput


def connect(db_path: str) -> sqlite3.Connection:
    """创建数据库连接，开启外键约束"""
    conn = sqlite3.connect(db_path)  # 打开数据库文件
    conn.execute("PRAGMA foreign_keys = ON;")  # 开启外键检查
    return conn  # 返回连接对象


def init_db(db_path: str, schema_path: str = "db/schema.sql") -> None:
    """
    初始化数据库,只加载主表schema(middle_school/high_school/student/plan/quota_plan/self_recruit_eligibility/volunteer）
    ⚠【W1警告】本函数会直接删除整个db文件!
    包含run/log运行结果的数据库严禁调用此函数,只用于全新初始化！
    run/log表由1号、3号脚本分别执行schema_run.sql、schema_log.sql
    建表顺序严格遵守契约:schema.sql → schema_run.sql → schema_log.sql
    """
    if os.path.exists(db_path):  # 判断库文件是否已经存在
        os.remove(db_path)  # 删除旧数据库文件
    conn = connect(db_path)  # 新建连接
    with open(schema_path, "r", encoding="utf-8") as f:  # 打开schema脚本
        sql_text = f.read()  # 读取全部sql文本
    conn.executescript(sql_text)  # 执行建表脚本
    conn.commit()  # 提交事务
    conn.close()  # 关闭连接


def _insert_many(conn: sqlite3.Connection, dataset: Dataset):
    """内部函数,循环批量insert写入内存Dataset;注意:外层必须控制事务commit/rollback"""
    for m in dataset.middle_schools:  # 循环插入初中
        conn.execute(
            "INSERT INTO middle_school(school_id,name,district) VALUES (?,?,?)",
            (m.school_id, m.name, m.district)
        )
    for h in dataset.high_schools:  # 循环插入高中
        conn.execute(
            "INSERT INTO high_school(school_id,name,type,recruit_batch) VALUES (?,?,?,?)",
            (h.school_id, h.name, h.type, h.recruit_batch)
        )
    for s in dataset.students:  # 循环插入考生
        conn.execute(
            "INSERT INTO student(student_id,name,junior_school_id,score,tie_seq) VALUES (?,?,?,?,?)",
            (s.student_id, s.name, s.junior_school_id, s.score, s.tie_seq)
        )
    for p in dataset.plans:  # 循环插入招生计划
        conn.execute(
            "INSERT INTO plan(plan_id,year,high_school_id,batch,category,quota,control_line,remaining) VALUES (?,?,?,?,?,?,?,?)",
            (p.plan_id, p.year, p.high_school_id, p.batch, p.category, p.quota, p.control_line, p.remaining)
        )
    for q in dataset.quota_plans:  # 循环插入名额分配子计划
        conn.execute(
            "INSERT INTO quota_plan(plan_id,junior_school_id,quota) VALUES (?,?,?)",
            (q.plan_id, q.junior_school_id, q.quota)
        )
    for e in dataset.self_recruit_eligibilities:  # 循环插入自招资格
        conn.execute(
            "INSERT INTO self_recruit_eligibility(student_id,high_school_id,status,rank) VALUES (?,?,?,?)",
            (e.student_id, e.high_school_id, e.status, e.rank)
        )
    for v in dataset.volunteers:  # 循环插入志愿
        conn.execute(
            "INSERT INTO volunteer(year,student_id,batch,seq,plan_id) VALUES (?,?,?,?,?)",
            (v.year, v.student_id, v.batch, v.seq, v.plan_id)
        )


def write_dataset(conn: sqlite3.Connection, dataset: Dataset) -> List[Issue]:
    """
    W2升级:入库前执行validate内存校验;统计导入耗时;约束冲突回滚抛异常,不静默吞错误 R39
    :param conn: 已经打开的数据库连接(外部不要在这里open/close,便于多次复用)
    :param dataset: 待写入内存Dataset对象
    :return: 校验出来的Issue列表;非空代表校验不通过,禁止写入
    """
    from src.validate import validate  # 延迟导入，避免循环import

    issues: List[Issue] = validate(dataset)  # W2：先做内存层全套静态校验
    if len(issues) > 0:
        # 内存校验发现错误，直接返回issue，不触碰数据库
        return issues

    start_time = time.perf_counter()  # 记录导入开始时间，W2统计耗时
    try:
        _insert_many(conn, dataset)  # 调用批量插入
        conn.commit()  # 提交写入事务
        elapsed = time.perf_counter() - start_time
        print(f"[write_dataset]导入完成，耗时={elapsed:.3f}秒")
    except sqlite3.IntegrityError as e:  # 捕获主键/唯一/外键冲突数据库层异常
        conn.rollback()  # 全部回滚，避免半写状态
        raise RuntimeError(f"数据集数据库完整性约束失败：{str(e)}") from e
    return issues


def write_results(conn: sqlite3.Connection, run_out: RunOutput):
    """
    W2占位函数:写入投档模拟运行输出RunOutput
    实际实现由3号主要负责,2号预留对外接口;
    run、admit_result、admit_log、carry_log属于schema_run.sql / schema_log.sql,本模块不建表
    """
    raise NotImplementedError("write_results 投档结果写入,由3号实现,W2预留接口签名")
