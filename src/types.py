from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import json


@dataclass
class Student:
    """考生实体"""
    student_id: str        # 考生唯一编号
    name: str              # 考生姓名
    junior_school_id: str  # 所属初中编号
    total_score: int       # 中考总分
    same_rank_no: int      # 同分序号：总分相同的学生内部排序编号，同总分内唯一


@dataclass
class JuniorSchool:
    """初中学校实体"""
    school_id: str  # 初中编号
    name: str       # 初中名称


@dataclass
class SeniorSchool:
    """高中学校实体"""
    school_id: str         # 高中编号
    name: str              # 高中名称
    batch_list: List[int]  # 该高中参与招生的批次，例如只参加第四批就是 [4]


@dataclass
class SelfRecruitQualify:
    """自主招生资格：考生获得某高中自招入围资格"""
    student_id: str        # 考生编号
    senior_school_id: str  # 高中编号
    rank: int              # 校内自招考核排名


@dataclass
class AdmissionPlan:
    """招生计划：一条招生名额记录（统招/名额分配/自招）"""
    plan_id: str                # 计划唯一ID
    year: int                   # 招生年份
    senior_school_id: str       # 高中编号
    junior_school_id: Optional[str] # 名额分配才绑定初中；统招、自招填 None
    batch: int                  # 招生批次
    category: str               # 计划类型："自主招生" / "名额分配" / "统招"
    initial_quota: int          # 初始名额总数
    current_remain: int         # 当前剩余名额（冗余字段，方便投档逻辑）
    control_line: int           # 该计划分数线/控制线


@dataclass
class Volunteer:
    """考生志愿"""
    year: int         # 招生年份
    student_id: str   # 考生编号
    plan_id: str      # 对应招生计划ID
    batch: int        # 志愿所属批次
    vol_no: int       # 志愿序号：同一个考生、同一个批次内志愿序号不能重复


@dataclass
class CarryOverLog:
    """名额结转日志：名额从本批次流转到下一批次的记录"""
    run_id: str             # 本次模拟运行ID
    source_batch: int       # 源批次
    target_batch: int       # 转入目标批次
    senior_school_id: str   # 高中编号
    from_junior_id: Optional[str] # 原绑定初中（名额分配结转才有效）
    transfer_count: int     # 结转名额数量
    transfer_time: str      # 结转时间


@dataclass
class AdmissionLog:
    """投档录取单条日志"""
    run_id: str        # 本次模拟运行ID
    student_id: str    # 考生编号
    plan_id: str       # 录取到的招生计划
    result_code: str   # 结果码：录取/退档/滑档等标记
    remark: str        # 备注说明
    remain_before: int # 投档前计划剩余名额
    remain_after: int  # 投档后计划剩余名额


@dataclass
class Issue:
    """数据校验异常信息"""
    level: str    # 级别：ERROR 错误 / WARN 警告
    msg: str      # 异常描述文本
    entity_type: str # 出错实体类型 student / volunteer / plan
    entity_id: str   # 出错实体ID


@dataclass
class Dataset:
    """整套输入数据集，一次模拟的全部原始数据"""
    year: int
    seed: int                     # 随机种子，保证复现
    junior_schools: List[JuniorSchool]
    senior_schools: List[SeniorSchool]
    students: List[Student]
    self_recruit_list: List[SelfRecruitQualify]
    plan_list: List[AdmissionPlan]
    volunteer_list: List[Volunteer]


@dataclass
class RunOutput:
    """模拟运行输出结果包"""
    dataset: Dataset
    admit_logs: List[AdmissionLog]
    carry_logs: List[CarryOverLog]
    issues: List[Issue]


def to_json(obj):
    """dataclass 对象转JSON,调试、打印输出用"""
    return json.dumps(obj, default=lambda o: o.__dict__, ensure_ascii=False, indent=2)
