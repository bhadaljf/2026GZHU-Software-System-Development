"""规则参数读取（1 号）。

职责：把 config/rules.toml 读成 dict 并做结构校验，作为引擎与查询层的唯一参数入口。
入参：path，缺省为项目根下的 config/rules.toml。
出参：dict，键为 year / control_line / gradient / plan_ratio /
      batch_volunteer_limit / data / run。

不提供“运行期覆盖”能力：一次运行的参数要落进 run.params_json 存照（R36）。
"""

import tomllib
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "config" / "rules.toml"

REQUIRED_TOP = (
    "year",
    "control_line",
    "gradient",
    "plan_ratio",
    "batch_volunteer_limit",
    "data",
)


def load_rules(path=None) -> dict:
    """读取并校验规则参数。结构不合法时抛 ValueError，不做静默兜底。"""
    rule_path = Path(path) if path else DEFAULT_PATH
    with open(rule_path, "rb") as f:
        rules = tomllib.load(f)
    _validate(rules, rule_path)
    return rules


def _validate(rules: dict, rule_path: Path) -> None:
    missing = [k for k in REQUIRED_TOP if k not in rules]
    if missing:
        raise ValueError(f"{rule_path} 缺少字段: {', '.join(missing)}")

    if int(rules["year"]) < 2000:
        raise ValueError("year 不合理")
    if int(rules["control_line"]) <= 0:
        raise ValueError("control_line 必须为正")

    gradient = rules["gradient"]
    for key in ("first_line", "delta"):
        if key not in gradient:
            raise ValueError(f"gradient 缺少 {key}")
    if gradient["first_line"] <= rules["control_line"]:
        raise ValueError("first_line（G₁）应高于 control_line（L）")
    if gradient["delta"] <= 0:
        raise ValueError("gradient.delta 必须为正")

    ratio = rules["plan_ratio"]
    for key in ("self_recruit_cap", "quota_ratio"):
        if key not in ratio:
            raise ValueError(f"plan_ratio 缺少 {key}")
        if not 0 < ratio[key] <= 1:
            raise ValueError(f"plan_ratio.{key} 应在 (0, 1] 区间")
    if ratio["self_recruit_cap"] + ratio["quota_ratio"] > 1:
        raise ValueError("自招上限与名额分配比例之和超过总计划")

    limits = rules["batch_volunteer_limit"]
    for batch in range(1, 5):
        key = f"batch{batch}"
        if key not in limits or int(limits[key]) <= 0:
            raise ValueError(f"batch_volunteer_limit.{key} 缺失或不为正")

    data = rules["data"]
    for key in ("seed", "students", "middle_schools", "high_schools"):
        if key not in data:
            raise ValueError(f"data 缺少 {key}")
        if int(data[key]) <= 0:
            raise ValueError(f"data.{key} 必须为正")


def batch_limit(rules: dict, batch: int) -> int:
    """某批次的志愿上限（R7）。"""
    return int(rules["batch_volunteer_limit"][f"batch{batch}"])


def gradient_lines(rules: dict) -> list:
    """从 G₁ 逐档下移直至 L 的梯度线列表，含 G₁ 与 L 本身（R11）。

    例：G₁=712、Δ=40、L=492 → [712, 672, 632, 592, 552, 512, 492]
    """
    g1 = int(rules["gradient"]["first_line"])
    delta = int(rules["gradient"]["delta"])
    floor = int(rules["control_line"])
    lines = [g1]
    while lines[-1] - delta > floor:
        lines.append(lines[-1] - delta)
    lines.append(floor)
    return lines
