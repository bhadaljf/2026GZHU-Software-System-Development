# src/types.py
# 维护人：2号 W1
# 依据：docs/00_契约.md v0.9，docs/01_需求与规则清单.md v1.0
from dataclasses import dataclass # 导入数据类装饰器
from typing import Optional, List # 导入类型提示


@dataclass
class Issue:
    """校验异常对象 R39"""
    level: str # "error"严重错误｜"warn"警告
    table: str # 出错表名
    key: str # 出错记录主键字符串
    message: str # 错误描述，附带R编号


@dataclass
class MiddleSchool:
    """初中实体"""
    school_id: str # 初中唯一ID
    name: str # 初中名称
    district: str # 行政区


@dataclass
class HighSchool:
    """高中实体 R6"""
    school_id: str # 高中唯一ID
    name: str # 高中名称
    type: str # 学校类型示范/普通
    recruit_batch: int # 统招接收批次，只能3/4 R6


@dataclass
class Student:
    """考生实体"""
    student_id: str # 考生编号
    name: str # 考生姓名
    junior_school_id: str # 所属初中ID R23
    score: int # 中考总分唯一投档依据 R3
    tie_seq: int # 同分序号，越小越优先 R16/R39


@dataclass
class Plan:
    """招生计划实体"""
    plan_id: str # 计划唯一ID
    year: int # 模拟年度
    high_school_id: str # 归属高中ID
    batch: int # 批次1‑4
    category: str # self_recruit/quota/unified
    quota: int # 初始名额 R5
    control_line: int # 计划控制线≥492 R10
    remaining: int # 当前剩余名额冗余字段 R29


@dataclass
class QuotaPlan:
    """名额分配子计划 R22"""
    plan_id: str # 主计划ID外键
    junior_school_id: str # 初中ID外键
    quota: int # 分配到此初中名额


@dataclass
class SelfRecruitEligibility:
    """自招资格记录 R20"""
    student_id: str # 考生ID
    high_school_id: str # 高中ID
    status: str # 资格状态ok/invalid
    rank: int # 校内考核排名 R21


@dataclass
class Volunteer:
    """考生志愿 R7"""
    year: int # 模拟年度
    student_id: str # 考生ID
    batch: int # 志愿批次
    seq: int # 志愿序号从1开始
    plan_id: str # 报考计划ID


@dataclass
class Dataset:
    """完整内存数据集 R8"""
    middle_schools: List[MiddleSchool] # 初中集合
    high_schools: List[HighSchool] # 高中集合
    students: List[Student] # 考生集合
    plans: List[Plan] # 招生计划集合
    quota_plans: List[QuotaPlan] # 名额分配子计划集合
    self_recruit_eligibilities: List[SelfRecruitEligibility] #自招资格集合
    volunteers: List[Volunteer] #志愿集合
    data_version: str #数据集版本标记
    seed: Optional[int] = None #随机种子，保证复现 R8


@dataclass
class RunOutput:
    """引擎输出占位,业务归3号"""
    run_id: str #运行唯一编号
