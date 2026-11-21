"""导入校验（2 号）。

拦截：重复考生、非法分数、重复志愿、无效计划、同分序号重复、计划超额。
报错须给出定位信息（表、行、主键），不吞异常。
"""

# src/validate.py
"""导入校验(2号)。
拦截：重复考生、非法分数、重复志愿、无效计划、同分序号重复、计划超额。
报错须给出定位信息（表、行、主键），不吞异常。
"""
from typing import List, Dict
from src.types import Dataset, Issue


def validate(dataset: Dataset) -> List[Issue]:
    """内存数据集全套静态校验，返回错误列表 R39"""
    issues: List[Issue] = [] # 初始化错误收集列表

    mid_school_ids = {m.school_id for m in dataset.middle_schools} #收集全部初中ID
    high_school_ids = {h.school_id for h in dataset.high_schools} #收集全部高中ID
    student_ids = {s.student_id for s in dataset.students} #收集全部考生ID
    plan_ids = {p.plan_id for p in dataset.plans} #收集全部计划ID

    # 【重复考生校验】考生主键唯一
    if len(student_ids) != len(dataset.students):
        seen = set()
        for s in dataset.students:
            if s.student_id in seen:
                issues.append(Issue(
                    level="error", table="student", key=s.student_id,
                    message=f"重复考生student_id={s.student_id}"
                ))
            seen.add(s.student_id)

    for hs in dataset.high_schools: #遍历全部高中做校验
        if hs.recruit_batch not in (3, 4): # 判断接收批次非法 R6
            issues.append(Issue( #追加错误
                level="error", table="high_school", key=hs.school_id,
                message=f"recruit_batch={hs.recruit_batch}, 只能为3或4(R6)"
            ))

    high_recruit_map: Dict[str, int] = {h.school_id: h.recruit_batch for h in dataset.high_schools} #构建高中‑接收批次映射
    for p in dataset.plans: #遍历全部招生计划
        rt = high_recruit_map.get(p.high_school_id) #取出该高中的统招接收批次
        if rt == 4 and p.batch in (1, 2): #4批高中禁止1/2批计划 R6
            issues.append(Issue(
                level="error", table="plan", key=p.plan_id,
                message=f"该高中recruit_batch=4,禁止batch={p.batch}计划(R6)"
            ))
        if p.control_line < 492: #计划控制线小于最低线L R10
            issues.append(Issue(
                level="error", table="plan", key=p.plan_id,
                message=f"计划控制线{p.control_line},不得小于L=492(R10)"
            ))
        if p.quota < 0 or p.remaining < 0: #计划名额超额/负数
            issues.append(Issue(
                level="error", table="plan", key=p.plan_id,
                message=f"计划名额非法,quota={p.quota}, remaining={p.remaining}"
            ))

    for st in dataset.students: #遍历考生校验分数
        if not (0 <= st.score <= 750): #分数越界判断 R39
            issues.append(Issue(
                level="error", table="student", key=st.student_id,
                message=f"非法分数score={st.score}(R39)"
            ))

    seen_score_tie = set() #集合存储已经出现过的(分数,同分序号)
    for st in dataset.students: #遍历考生检查同分序号重复
        key = (st.score, st.tie_seq) #组装联合key
        if key in seen_score_tie: #检测重复 R39
            issues.append(Issue(
                level="error", table="student", key=st.student_id,
                message=f"同总分{st.score}下重复tie_seq={st.tie_seq}(R39)"
            ))
        seen_score_tie.add(key) #加入已看见集合

    seen_high_rank = set() #存储(高中id,rank)集合
    for e in dataset.self_recruit_eligibilities: #遍历自招资格
        k = (e.high_school_id, e.rank) #组装联合key
        if k in seen_high_rank: #同高中rank重复 R21
            issues.append(Issue(
                level="error", table="self_recruit_eligibility", key=f"{e.student_id},{e.high_school_id}",
                message=f"同一高中{e.high_school_id}重复考核rank={e.rank}(R21)"
            ))
        seen_high_rank.add(k) #加入集合

    batch_max_seq = {1: 1, 2: 3, 3: 6, 4: 6} #各批次志愿最大上限 R7
    seen_volunteer_key = set() #用于检测重复志愿
    for v in dataset.volunteers: #遍历志愿
        limit = batch_max_seq.get(v.batch, 0) #取出该批次最大序号
        if v.seq > limit: #志愿序号超限 R7
            issues.append(Issue(
                level="error", table="volunteer", key=f"{v.year},{v.student_id},{v.batch},{v.seq}",
                message=f"批次{v.batch}志愿序号{v.seq}超过上限{limit}(R7)"
            ))
        # 重复志愿校验（year+student_id+batch+seq唯一）
        vk = (v.year, v.student_id, v.batch, v.seq)
        if vk in seen_volunteer_key:
            issues.append(Issue(
                level="error", table="volunteer", key=f"{v.year},{v.student_id},{v.batch},{v.seq}",
                message=f"重复志愿记录(year,student_id,batch,seq)"
            ))
        seen_volunteer_key.add(vk)

    # 外键校验
    for s in dataset.students: #考生外键检查：初中id存在
        if s.junior_school_id not in mid_school_ids: #引用不存在初中
            issues.append(Issue(level="error", table="student", key=s.student_id,
                                message=f"不存在的初中id {s.junior_school_id}"))
    for p in dataset.plans: #计划外键检查：高中id存在
        if p.high_school_id not in high_school_ids: #引用不存在高中
            issues.append(Issue(level="error", table="plan", key=p.plan_id,
                                message=f"不存在的高中id {p.high_school_id}"))
    for qp in dataset.quota_plans: #名额分配外键校验
        if qp.plan_id not in plan_ids: #plan_id不存在
            issues.append(Issue(level="error", table="quota_plan", key=f"{qp.plan_id},{qp.junior_school_id}",
                                message=f"plan_id不存在 {qp.plan_id}"))
        if qp.junior_school_id not in mid_school_ids: #初中id不存在
            issues.append(Issue(level="error", table="quota_plan", key=f"{qp.plan_id},{qp.junior_school_id}",
                                message=f"junior_school_id不存在 {qp.junior_school_id}"))
    for v in dataset.volunteers: #志愿外键校验
        if v.student_id not in student_ids: #考生id不存在
            issues.append(Issue(level="error", table="volunteer", key=f"{v.year},{v.student_id},{v.batch},{v.seq}",
                                message=f"student_id不存在 {v.student_id}"))
        if v.plan_id not in plan_ids: #计划id不存在
            issues.append(Issue(level="error", table="volunteer", key=f"{v.year},{v.student_id},{v.batch},{v.seq}",
                                message=f"plan_id不存在 {v.plan_id}"))

    return issues #返回全部校验结果
