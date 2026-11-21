"""原因码字典（4 号：黎俊彤）。

职责：维护未录取原因码与中文文案的唯一出处。
码值与文案严格照抄 docs/00_契约.md 第 3 节，禁止自行改码值；
6 号用 all_reasons() 渲染下拉框/图例，5 号用 describe() 核对文案。

入参：code（str）
出参：describe -> str；all_reasons -> list[dict]（[{"code","text","batches"}]）
"""

from __future__ import annotations

# 码 -> 中文文案（契约第 3 节，R01—R07）
REASON_CODES: dict[str, str] = {
    "R01": "未达计划控制线或最低控制线",
    "R02": "计划名额已满",
    "R03": "不在自主招生资格名单或排名不达",
    "R04": "前批已录取",
    "R05": "非所属初中名额",
    "R06": "志愿或计划无效",
    "R07": "未填报该计划",
}

# 码 -> 适用批次（给 5 号核对“该批次不该出现这个码”用）
REASON_BATCHES: dict[str, tuple[int, ...]] = {
    "R01": (1, 2, 3, 4),
    "R02": (1, 2, 3, 4),
    "R03": (1,),
    "R04": (2, 3, 4),
    "R05": (2,),
    "R06": (1, 2, 3, 4),
    "R07": (1, 2, 3, 4),
}

# 无法识别的码统一文案（不报错，便于对账时把脏数据暴露出来）
UNKNOWN_TEXT = "未知原因"


def describe(code: str | None) -> str:
    """码 -> 中文文案；空码返回“-”，未知码返回“未知原因”。"""
    if code is None or code == "":
        return "-"
    return REASON_CODES.get(str(code).strip().upper(), UNKNOWN_TEXT)


def codes() -> list[str]:
    """全部原因码（按码值升序）。"""
    return sorted(REASON_CODES)


def all_reasons() -> list[dict]:
    """全部原因码 + 文案 + 适用批次，供 GET /api/reasons 与页面图例使用。"""
    return [
        {"code": c, "text": REASON_CODES[c], "batches": list(REASON_BATCHES.get(c, ())), }
        for c in codes()
    ]


def is_valid(code: str | None) -> bool:
    """是否是契约内的合法原因码。"""
    return code is not None and str(code).strip().upper() in REASON_CODES
