"""投档引擎公共接口（3 号）。"""

from .bands import assign_band
from .batch import BatchOutcome, EngineState, run_unified
from .quota import carry_over, run_quota_alloc, run_self_recruit
from .runner import RunOutput, run_all, run_batches

__all__ = [
    "assign_band",
    "BatchOutcome",
    "EngineState",
    "RunOutput",
    "run_unified",
    "run_self_recruit",
    "run_quota_alloc",
    "carry_over",
    "run_all",
    "run_batches",
]

