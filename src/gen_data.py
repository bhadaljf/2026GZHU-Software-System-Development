"""两档虚构数据生成(2 号)。
数据规模取 config/rules.toml 的 data 段:小数据集供对账,15 万规模数据供演示。
同一 seed 与同一配置重复生成结果一致。
"""
# W1 2号成员；W1：small完整实现；large=15万W2补齐，遵循计划切分规则、正态分数、冲稳保志愿
import random  # 导入随机数模块，用来生成随机考生、志愿、名额
import tomllib  # 导入toml解析库，读取rules.toml配置
import json
import os
import dataclasses
from typing import List, Dict  # 导入类型提示，方便静态检查
from src.types import (Dataset, MiddleSchool, HighSchool, Student,
                        Plan, QuotaPlan, SelfRecruitEligibility, Volunteer)  # 导入全部数据类


def generate(scale: str, out_dir: str, seed: int) -> Dataset:
    """
    生成模拟数据集,seed保证可复现 R8
    :param scale: "small"小数据集 / "large"15万规模
    :param out_dir: 输出目录(small用来序列化落盘,large不落地)
    :param seed: 随机种子,固定seed保证每次生成结果完全一致
    :return: Dataset内存数据集对象,包含学校、考生、计划、志愿等全部数据
    """
    rng = random.Random(seed)  # 实例化随机对象，绑定种子，全局复用这个rng保证一致性
    year = 2026  # 模拟招生年度，固定
    data_version = f"{scale}-v1-seed{seed}"  # 数据集版本字符串，用于快照标记

    if scale == "small":
        # ========== small 小数据集【W1完整实现，用于对账推演】==========
        mid_schools = [  # 初始化2所初中，用于小样本对账测试
            MiddleSchool(school_id="M01", name="初中A", district="A区"),
            MiddleSchool(school_id="M02", name="初中B", district="B区"),
        ]

        high_schools = [  # 初始化4所高中，H01/H02=3批次；H03/H04=4批次
            HighSchool(school_id="H01", name="示范高中1", type="demo", recruit_batch=3),
            HighSchool(school_id="H02", name="示范高中2", type="demo", recruit_batch=3),
            HighSchool(school_id="H03", name="普高3", type="normal", recruit_batch=4),
            HighSchool(school_id="H04", name="普高4", type="normal", recruit_batch=4),
        ]

        students: List[Student] = []  # 考生空列表，存放生成的考生对象
        used_score_tie = set()  # 记录已经占用(score,tie_seq)，保证同分序号全局唯一
        for idx in range(16):  # 循环生成16个考生，small固定16人
            sid = f"S{idx:02d}"  # 生成考生编号，S00~S15
            name = f"考生{idx}"  # 生成考生姓名
            j_sid = rng.choice(["M01", "M02"])  # 随机分配所属初中
            while True:  # 循环直到找到不重复的分数+同分序号
                score = rng.randint(450, 740)  # 随机分数区间450‑740
                tie_seq = rng.randint(1, 200)  # 随机同分序号，用来区分同分考生
                if (score, tie_seq) not in used_score_tie:  # 判断这个组合没有被占用
                    used_score_tie.add((score, tie_seq))  # 加入占用集合标记
                    break  # 跳出while循环，拿到合法唯一的(分数,同分序号)
            students.append(Student(
                student_id=sid,
                name=name,
                junior_school_id=j_sid,
                score=score,
                tie_seq=tie_seq
            ))  # 组装考生对象，加入考生列表

        plans = [  # W1手动预切分计划；自动切分逻辑在large分支实现
            Plan(plan_id="P01", year=year, high_school_id="H01", batch=1, category="self_recruit", quota=4, control_line=500, remaining=4),
            Plan(plan_id="P02", year=year, high_school_id="H01", batch=2, category="quota", quota=10, control_line=492, remaining=10),
            Plan(plan_id="P03", year=year, high_school_id="H01", batch=3, category="unified", quota=16, control_line=492, remaining=16),
            Plan(plan_id="P04", year=year, high_school_id="H02", batch=1, category="self_recruit", quota=2, control_line=520, remaining=2),
            Plan(plan_id="P05", year=year, high_school_id="H02", batch=2, category="quota", quota=8, control_line=492, remaining=8),
            Plan(plan_id="P06", year=year, high_school_id="H02", batch=3, category="unified", quota=12, control_line=492, remaining=12),
            Plan(plan_id="P07", year=year, high_school_id="H03", batch=4, category="unified", quota=20, control_line=492, remaining=20),
            Plan(plan_id="P08", year=year, high_school_id="H04", batch=4, category="unified", quota=18, control_line=492, remaining=18),
        ]

        quota_plans = [  # 名额分配子计划，绑定plan_id和初中，指标到校
            QuotaPlan(plan_id="P02", junior_school_id="M01", quota=6),
            QuotaPlan(plan_id="P02", junior_school_id="M02", quota=4),
            QuotaPlan(plan_id="P05", junior_school_id="M01", quota=5),
            QuotaPlan(plan_id="P05", junior_school_id="M02", quota=3),
        ]

        self_recruit: List[SelfRecruitEligibility] = []  # 自招资格空列表，存放获得自招资格考生
        rank_h01 = 1  # H01自招rank起始值，自招排名从1开始
        rank_h02 = 1  # H02自招rank起始值
        for s in students[:6]:  # 取前6位考生，随机发放H01自招资格
            if rng.random() > 0.4:  # 随机概率0.6发放资格
                self_recruit.append(SelfRecruitEligibility(student_id=s.student_id, high_school_id="H01", status="ok", rank=rank_h01))
                rank_h01 += 1  # rank自增，保证该高中内排名唯一
        for s in students[8:14]:  # 取部分考生给H02自招资格
            if rng.random() > 0.5:  # 随机概率0.5发放资格
                self_recruit.append(SelfRecruitEligibility(student_id=s.student_id, high_school_id="H02", status="ok", rank=rank_h02))
                rank_h02 += 1  # rank自增，保证该高中内排名唯一

        volunteers: List[Volunteer] = []  # 志愿空列表，存放所有考生志愿记录
        batch_plan_map = {  # 批次‑可选计划映射：每个批次可以选哪些plan
            1: ["P01", "P04"],
            2: ["P02", "P05"],
            3: ["P03", "P06"],
            4: ["P07", "P08"],
        }
        batch_max = {1: 1, 2: 3, 3: 6, 4: 6}  # 各批次志愿最大上限，和规则文档对齐R7
        for st in students:  # 遍历每个考生，生成该考生全部批次志愿
            for b in [1, 2, 3, 4]:  # 循环4个招生批次
                max_seq = batch_max[b]  # 取出本批次最多能填几条志愿
                avail_plans = batch_plan_map[b]  # 取出该批次可选计划id列表
                pick_cnt = rng.randint(0, max_seq)  # 随机选多少条志愿，允许0条（不填）
                chosen = rng.sample(avail_plans, k=min(pick_cnt, len(avail_plans)))  # 不重复抽样志愿
                for idx, pid in enumerate(chosen):  # 遍历选中计划，生成志愿记录
                    seq = idx + 1  # 志愿序号从1开始
                    volunteers.append(Volunteer(
                        year=year,
                        student_id=st.student_id,
                        batch=b,
                        seq=seq,
                        plan_id=pid
                    ))

        ds = Dataset(  # 组装完整Dataset对象，打包所有维度数据
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
        # ========== W2：15万规模生成器完整实现【遵循需求规则R5/R6/R7/R8/R21/R39】 ==========
        # 规则：3批高中：总计划 → 自招≤10% → 指标到校50% → 剩余统招；4批高中仅统招
        # 500初中、150公办高中；分数正态分布；志愿冲稳保；seed可复现
        with open("config/rules.toml", "rb") as f:  # 二进制打开toml配置文件，tomllib要求rb模式
            cfg = tomllib.load(f)  # 解析toml配置到字典
            data_cfg = cfg["data"]  # 读取data段：15w、500初中、150高中
            total_stu = data_cfg["students"]  # 总考生数量：150000
            n_mid = data_cfg["middle_schools"]  # 初中总数：500
            n_high = data_cfg["high_schools"]  # 高中总数：150
            control_line = cfg["control_line"]  # 投档控制线，从配置读取
            plan_ratio = cfg["plan_ratio"]
            self_recruit_cap = plan_ratio["self_recruit_cap"]  # 自招上限0.1
            quota_ratio = plan_ratio["quota_ratio"]  # 指标到校0.5

        # 一次性生成全部初中（所有批次共用）
        mid_schools: List[MiddleSchool] = []
        for sid in range(n_mid):
            mid_schools.append(MiddleSchool(
                school_id=f"M{sid:04d}",  # 初中ID M0000~M0499，固定4位
                name=f"初中_{sid:04d}",  # 初中名称
                district=f"片区{sid % 8}"  # 片区循环8个区域，均匀分配
            ))

        # 一次性生成全部高中 + 按规则切分招生计划 R5 R6
        high_schools: List[HighSchool] = []
        plans: List[Plan] = []
        batch_plan_map = {1: [], 2: [], 3: [], 4: []}  # 按批次归集plan_id，给志愿生成用
        high_score_base = dict()  # 记录每个高中基准分数线，用于冲稳保志愿排序
        pid_seq = 0  # 计划id自增计数器

        for sid in range(n_high):
            # 40%为3批次高中，60%为4批次高中；recruit_batch只允许3/4，契约约束
            is_batch3 = rng.random() < 0.40
            if is_batch3:
                recruit_batch = 3
            else:
                recruit_batch = 4
            hs = HighSchool(
                school_id=f"H{sid:03d}",  # 高中ID H000~H149，3位编号
                name=f"高中_{sid:03d}",
                type="公办",
                recruit_batch=recruit_batch
            )
            high_schools.append(hs)
            base_score = rng.randint(492, 700)
            high_score_base[hs.school_id] = base_score

            if recruit_batch == 4:
                # 第四批高中：仅统招计划，R6不生成1、2批次计划
                total_quota = rng.randint(60, 220)
                pid = f"P{pid_seq:05d}"
                pid_seq += 1
                p = Plan(
                    plan_id=pid,
                    year=year,
                    high_school_id=hs.school_id,
                    batch=4,
                    category="unified",
                    quota=total_quota,
                    control_line=control_line,
                    remaining=total_quota
                )
                plans.append(p)
                batch_plan_map[4].append(pid)
            else:
                # 第三批高中：一套总名额，切分自招、指标到校、统招 R5
                total_quota = rng.randint(80, 260)
                sr_quota = int(total_quota * self_recruit_cap)   # ≤总计划10%，int截断微小偏差模拟允许
                quota_quota = int(total_quota * quota_ratio)     # 总计划50%
                uni_quota = total_quota - sr_quota - quota_quota

                # 1批次：自招计划
                if sr_quota > 0:
                    pid = f"P{pid_seq:05d}"
                    pid_seq += 1
                    p = Plan(
                        plan_id=pid, year=year, high_school_id=hs.school_id,
                        batch=1, category="self_recruit", quota=sr_quota,
                        control_line=base_score, remaining=sr_quota
                    )
                    plans.append(p)
                    batch_plan_map[1].append(pid)
                # 2批次：指标到校计划
                if quota_quota > 0:
                    pid = f"P{pid_seq:05d}"
                    pid_seq += 1
                    p = Plan(
                        plan_id=pid, year=year, high_school_id=hs.school_id,
                        batch=2, category="quota", quota=quota_quota,
                        control_line=control_line, remaining=quota_quota
                    )
                    plans.append(p)
                    batch_plan_map[2].append(pid)
                # 3批次：统招计划
                if uni_quota > 0:
                    pid = f"P{pid_seq:05d}"
                    pid_seq += 1
                    p = Plan(
                        plan_id=pid, year=year, high_school_id=hs.school_id,
                        batch=3, category="unified", quota=uni_quota,
                        control_line=base_score, remaining=uni_quota
                    )
                    plans.append(p)
                    batch_plan_map[3].append(pid)

        # 生成名额分配子计划（仅batch=2的quota计划才有quota_plan）R22
        quota_plans: List[QuotaPlan] = []
        quota_plan_list = [p for p in plans if p.category == "quota"]
        for p in quota_plan_list:
            assign_mid = rng.sample(mid_schools, k=rng.randint(3, 12))  # 分配到若干初中
            for m in assign_mid:
                quota_plans.append(QuotaPlan(
                    plan_id=p.plan_id,
                    junior_school_id=m.school_id,
                    quota=rng.randint(1, 8)
                ))

        # 分批生成考生、自招资格、志愿（控制内存，每批5000）
        batch_size = 5000
        total_batch = (total_stu + batch_size - 1) // batch_size  # 向上取整
        students: List[Student] = []
        self_recruit: List[SelfRecruitEligibility] = []
        volunteers: List[Volunteer] = []
        used_score_tie = set()  # R39 全局：全量考生分数+同分序号唯一，跨批次生效
        sr_rank_dict: Dict[str, int] = {}  # R21！按高中id独立维护自招rank，每个高中rank从1开始
        batch_max = {1: 1, 2: 3, 3: 6, 4: 6}  # 各批次志愿上限，和small保持一致R7

        # 预构建 pid -> 高中基准分映射，冲稳保排序用
        pid2score = {}
        for pl in plans:
            pid2score[pl.plan_id] = high_score_base[pl.high_school_id]

        for batch_idx in range(total_batch):
            start = batch_idx * batch_size  # 当前批次考生起始下标
            end = min(start + batch_size, total_stu)  # 当前批次考生结束下标
            print(f"【large生成】正在处理批次 {batch_idx+1}/{total_batch}，考生范围：{start} ~ {end-1}")

            # 循环生成本批次考生，分数正态分布（均值550，标准差90，截断350~740）
            for idx in range(start, end):
                sid = f"S{idx:08d}"  # 考生ID 8位，S00000000 ~ S00149999
                name = f"考生{idx}"
                j_sid = rng.choice(mid_schools).school_id  # 随机分配一所初中
                # 生成正态分数，模拟真实中考分布
                while True:
                    score = int(rng.normalvariate(mu=550, sigma=90))
                    score = max(350, min(740, score))
                    tie_seq = rng.randint(1, 200)
                    if (score, tie_seq) not in used_score_tie:
                        used_score_tie.add((score, tie_seq))
                        break
                stu = Student(
                    student_id=sid,
                    name=name,
                    junior_school_id=j_sid,
                    score=score,
                    tie_seq=tie_seq
                )
                students.append(stu)

                # 自招资格：仅1批次计划，分数≥控制线才有资格 R20；rank按高中独立计数R21
                batch1_pids = batch_plan_map[1]
                if len(batch1_pids) > 0 and rng.random() < 0.10:
                    sr_pid = rng.choice(batch1_pids)
                    sr_pl = [x for x in plans if x.plan_id == sr_pid][0]
                    sr_hid = sr_pl.high_school_id
                    if stu.score >= sr_pl.control_line:
                        # 该高中第一次发放rank初始化为1
                        if sr_hid not in sr_rank_dict:
                            sr_rank_dict[sr_hid] = 1
                        current_rank = sr_rank_dict[sr_hid]
                        self_recruit.append(SelfRecruitEligibility(
                            student_id=sid,
                            high_school_id=sr_hid,
                            status="ok",
                            rank=current_rank
                        ))
                        sr_rank_dict[sr_hid] += 1

                # 志愿生成：冲稳保逻辑，不再纯随机
                for b in [1, 2, 3, 4]:
                    max_seq = batch_max[b]
                    avail_pids = batch_plan_map[b]
                    if len(avail_pids) == 0:
                        continue
                    # 按考生分数和学校线差值排序：冲(高于自己分)、稳、保
                    def score_diff(pid):
                        return pid2score[pid] - stu.score
                    avail_pids_sorted = sorted(avail_pids, key=score_diff)
                    pick_cnt = rng.randint(0, max_seq)
                    pick_cnt = min(pick_cnt, len(avail_pids_sorted))
                    chosen = avail_pids_sorted[:pick_cnt]
                    for seq_idx, pid in enumerate(chosen):
                        seq = seq_idx + 1
                        volunteers.append(Volunteer(
                            year=year,
                            student_id=sid,
                            batch=b,
                            seq=seq,
                            plan_id=pid
                        ))

        # 组装最终Dataset，字段和small完全对齐，上层代码不用改动
        ds = Dataset(
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

    else:
        raise ValueError(f"不支持的scale参数:{scale},允许small/large")


def save_dataset(ds: Dataset, out_dir: str):
    """
    把Dataset序列化为json,保存到out_dir,配套load_dataset
    仅small数据集使用;large不落地文件
    :param ds: 内存里的Dataset对象
    :param out_dir: 输出文件夹，不存在则自动创建
    """
    os.makedirs(out_dir, exist_ok=True)
    raw = dataclasses.asdict(ds)
    out_path = os.path.join(out_dir, "dataset.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)


def load_dataset(out_dir: str) -> Dataset:
    """
    从out_dir加载序列化后的Dataset数据集
    契约接口:gen_data对外标准接口
    适用:small数据集(对账用,支持落盘加载)
    large数据集:业务上不落地静态文件，不使用该入口
    """
    json_path = os.path.join(out_dir, "dataset.json")
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"找不到数据集文件：{json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return Dataset(**raw)
