"""两档虚构数据生成（2 号）。

数据规模取 config/rules.toml 的 data 段：小数据集供对账，15 万规模数据供演示。
同一 seed 与同一配置重复生成结果一致。
"""

# src/gen_data.py W1
"""两档虚构数据生成(2号)。
数据规模取 config/rules.toml 的 data 段:小数据集供对账,15 万规模数据供演示。
同一 seed 与同一配置重复生成结果一致。
"""
# W1 2号成员；W1：small完整实现；large=15万仅首版骨架，W2完成内部逻辑
import random #导入随机数模块
from typing import List #导入类型提示
from src.types import (Dataset, MiddleSchool, HighSchool, Student,
                       Plan, QuotaPlan, SelfRecruitEligibility, Volunteer) #导入全部数据类


def generate(scale: str, out_dir: str, seed: int) -> Dataset:
    """
    生成模拟数据集,seed保证可复现 R8
    :param scale: "small"小数据集 / "large"15万规模(W1仅骨架,W2实现)
    :param out_dir: 输出目录
    :param seed: 随机种子，保证结果可复现
    :return: Dataset内存数据集对象
    """
    rng = random.Random(seed) #实例化随机对象，绑定种子
    year = 2026 #模拟年度
    data_version = f"{scale}-v1-seed{seed}" #数据集版本字符串

    if scale == "small":
        # ========== small 小数据集【W1完整实现】==========
        mid_schools = [ #初始化2所初中
            MiddleSchool(school_id="M01", name="初中A", district="A区"),
            MiddleSchool(school_id="M02", name="初中B", district="B区"),
        ]

        high_schools = [ #初始化4所高中，H01/H02=3；H03/H04=4 R6
            HighSchool(school_id="H01", name="示范高中1", type="demo", recruit_batch=3),
            HighSchool(school_id="H02", name="示范高中2", type="demo", recruit_batch=3),
            HighSchool(school_id="H03", name="普高3", type="normal", recruit_batch=4),
            HighSchool(school_id="H04", name="普高4", type="normal", recruit_batch=4),
        ]

        students: List[Student] = [] #考生空列表
        used_score_tie = set() #记录已经占用(score,tie_seq) R39
        for idx in range(16): #循环生成16个考生
            sid = f"S{idx:02d}" #生成考生编号
            name = f"考生{idx}" #生成考生姓名
            j_sid = rng.choice(["M01", "M02"]) #随机分配所属初中
            while True: #循环直到找到不重复的分数+同分序号
                score = rng.randint(450, 740) #随机分数450‑740
                tie_seq = rng.randint(1, 200) #随机同分序号
                if (score, tie_seq) not in used_score_tie: #判断没有重复
                    used_score_tie.add((score, tie_seq)) #加入占用集合
                    break #跳出while循环
            students.append(Student(student_id=sid, name=name, junior_school_id=j_sid, score=score, tie_seq=tie_seq)) #加入考生列表

        plans = [ #W1手动预切分计划；R5自动切分W2实现
            Plan(plan_id="P01", year=year, high_school_id="H01", batch=1, category="self_recruit", quota=4, control_line=500, remaining=4),
            Plan(plan_id="P02", year=year, high_school_id="H01", batch=2, category="quota", quota=10, control_line=492, remaining=10),
            Plan(plan_id="P03", year=year, high_school_id="H01", batch=3, category="unified", quota=16, control_line=492, remaining=16),
            Plan(plan_id="P04", year=year, high_school_id="H02", batch=1, category="self_recruit", quota=2, control_line=520, remaining=2),
            Plan(plan_id="P05", year=year, high_school_id="H02", batch=2, category="quota", quota=8, control_line=492, remaining=8),
            Plan(plan_id="P06", year=year, high_school_id="H02", batch=3, category="unified", quota=12, control_line=492, remaining=12),
            Plan(plan_id="P07", year=year, high_school_id="H03", batch=4, category="unified", quota=20, control_line=492, remaining=20),
            Plan(plan_id="P08", year=year, high_school_id="H04", batch=4, category="unified", quota=18, control_line=492, remaining=18),
        ]

        quota_plans = [ #名额分配子计划 R22
            QuotaPlan(plan_id="P02", junior_school_id="M01", quota=6),
            QuotaPlan(plan_id="P02", junior_school_id="M02", quota=4),
            QuotaPlan(plan_id="P05", junior_school_id="M01", quota=5),
            QuotaPlan(plan_id="P05", junior_school_id="M02", quota=3),
        ]

        self_recruit: List[SelfRecruitEligibility] = [] #自招资格空列表
        rank_h01 = 1 #H01自招rank起始值 R21
        rank_h02 = 1 #H02自招rank起始值 R21
        for s in students[:6]: #取前6位考生随机给H01自招资格
            if rng.random() > 0.4: #随机概率
                self_recruit.append(SelfRecruitEligibility(student_id=s.student_id, high_school_id="H01", status="ok", rank=rank_h01))
                rank_h01 += 1 #rank自增保证唯一
        for s in students[8:14]: #取部分考生给H02自招资格
            if rng.random() > 0.5: #随机概率
                self_recruit.append(SelfRecruitEligibility(student_id=s.student_id, high_school_id="H02", status="ok", rank=rank_h02))
                rank_h02 += 1 #rank自增

        volunteers: List[Volunteer] = [] #志愿空列表
        batch_plan_map = { #批次‑可选计划映射
            1: ["P01", "P04"],
            2: ["P02", "P05"],
            3: ["P03", "P06"],
            4: ["P07", "P08"],
        }
        batch_max = {1: 1, 2: 3, 3: 6, 4: 6} #各批次志愿最大上限 R7
        for st in students: #遍历每个考生生成志愿
            for b in [1, 2, 3, 4]: #循环4个批次
                max_seq = batch_max[b] #取出本批次最大志愿数
                avail_plans = batch_plan_map[b] #取出该批次可选计划
                pick_cnt = rng.randint(0, max_seq) #随机选多少条志愿
                chosen = rng.sample(avail_plans, k=min(pick_cnt, len(avail_plans))) #随机抽样计划
                for idx, pid in enumerate(chosen): #遍历选中计划生成志愿记录
                    seq = idx + 1 #志愿序号从1开始
                    volunteers.append(Volunteer(year=year, student_id=st.student_id, batch=b, seq=seq, plan_id=pid))

        ds = Dataset( #组装完整Dataset对象
            middle_schools=mid_schools,
            high_schools=high_schools,
            students=students,
            plans=plans,
            quota_plans=quota_plans,
            self_recruit_eligibilities=self_recruit,
            volunteers=volunteers,
            data_version=data_version,
            seed=seed
        )
        return ds

    elif scale == "large":
        # ========== W1：15万规模生成器【首版骨架，W2完整实现】 ==========
        # W2实现要点：500初中、150公办高中；分数贴近真实分布；冲稳保志愿；录取率56‑60%；seed可复现
        raise NotImplementedError("W1 large(15万)仅首版框架,完整实现移至W2阶段")

    else:
        raise ValueError(f"不支持的scale参数:{scale},允许small/large")


def load_dataset(out_dir: str) -> Dataset:
    """W1占位函数:从磁盘加载数据集,W2实现json反序列化"""
    raise NotImplementedError("W1 stub, implement later") #抛出未实现异常
