# src/store.py W1
# W1 2号成员；sqlite连接、初始化、批量写入
import sqlite3 #导入sqlite驱动
import os #导入文件系统操作
from typing import List #类型提示
from src.types import Dataset, Issue #导入自定义类型


def connect(db_path: str) -> sqlite3.Connection:
    """创建数据库连接，开启外键约束"""
    conn = sqlite3.connect(db_path) #打开数据库文件
    conn.execute("PRAGMA foreign_keys = ON;") #开启外键检查
    return conn #返回连接对象


def init_db(db_path: str, schema_path: str = "db/schema.sql") -> None:
    """初始化数据库,只加载主表schema
    ⚠【W1警告】本函数会直接删除整个db文件!
    包含run/log运行结果的数据库严禁调用此函数,只用于全新初始化！
    run/log表由1号、3号脚本分别执行schema_run.sql、schema_log.sql
    """
    if os.path.exists(db_path): #判断库文件是否已经存在
        os.remove(db_path) #删除旧数据库文件
    conn = connect(db_path) #新建连接
    with open(schema_path, "r", encoding="utf-8") as f: #打开schema脚本
        sql_text = f.read() #读取全部sql文本
    conn.executescript(sql_text) #执行建表脚本
    conn.commit() #提交事务
    conn.close() #关闭连接


def _insert_many(conn: sqlite3.Connection, dataset: Dataset):
    """内部函数,批量insert写入内存Dataset"""
    for m in dataset.middle_schools: #循环插入初中
        conn.execute("INSERT INTO middle_school(school_id,name,district) VALUES(?,?,?)",
                     (m.school_id, m.name, m.district))
    for h in dataset.high_schools: #循环插入高中
        conn.execute("INSERT INTO high_school(school_id,name,type,recruit_batch) VALUES(?,?,?,?)",
                     (h.school_id, h.name, h.type, h.recruit_batch))
    for s in dataset.students: #循环插入考生
        conn.execute("INSERT INTO student(student_id,name,junior_school_id,score,tie_seq) VALUES(?,?,?,?,?)",
                     (s.student_id, s.name, s.junior_school_id, s.score, s.tie_seq))
    for p in dataset.plans: #循环插入招生计划
        conn.execute("INSERT INTO plan(plan_id,year,high_school_id,batch,category,quota,control_line,remaining) VALUES(?,?,?,?,?,?,?,?)",
                     (p.plan_id, p.year, p.high_school_id, p.batch, p.category, p.quota, p.control_line, p.remaining))
    for q in dataset.quota_plans: #循环插入名额分配子计划
        conn.execute("INSERT INTO quota_plan(plan_id,junior_school_id,quota) VALUES(?,?,?)",
                     (q.plan_id, q.junior_school_id, q.quota))
    for e in dataset.self_recruit_eligibilities: #循环插入自招资格
        conn.execute("INSERT INTO self_recruit_eligibility(student_id,high_school_id,status,rank) VALUES(?,?,?,?)",
                     (e.student_id, e.high_school_id, e.status, e.rank))
    for v in dataset.volunteers: #循环插入志愿
        conn.execute("INSERT INTO volunteer(year,student_id,batch,seq,plan_id) VALUES(?,?,?,?,?)",
                     (v.year, v.student_id, v.batch, v.seq, v.plan_id))


def write_dataset(conn: sqlite3.Connection, dataset: Dataset) -> List[Issue]:
    """批量写入数据集；约束冲突抛异常，不静默吞错误 R39"""
    issues: List[Issue] = [] #预留错误列表
    try: #捕获数据库完整性异常
        _insert_many(conn, dataset) #调用批量插入
        conn.commit() #提交写入事务
    except sqlite3.IntegrityError as e: #捕获主键/唯一/外键冲突
        conn.rollback() #全部回滚，避免半写状态
        raise RuntimeError(f"数据集完整性约束失败：{str(e)}") from e #包装异常向上抛出
    return issues #返回问题列表
