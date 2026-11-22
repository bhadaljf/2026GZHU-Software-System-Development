"""梯度分档（3 号）。

职责：依据全市最低控制线 L、第一梯度线 G1 和梯度间隔 delta，
为考生分配唯一梯度档。返回 0 表示低于 L，不参与投档。
"""


def assign_band(score: int, rules: dict) -> int:
    """返回分数对应的梯度档，1 为最高档，0 表示低于 L。

    分数恰好等于某条梯度线时归入该线对应的较高梯度。
    """
    score = int(score)
    floor = int(rules["control_line"])
    first_line = int(rules["gradient"]["first_line"])
    delta = int(rules["gradient"]["delta"])

    if delta <= 0:
        raise ValueError("gradient.delta 必须为正")
    if first_line <= floor:
        raise ValueError("gradient.first_line 必须高于 control_line")
    if score < floor:
        return 0
    if score >= first_line:
        return 1

    return (first_line - score + delta - 1) // delta + 1

