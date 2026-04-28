from __future__ import annotations

import math
from dataclasses import dataclass

TIER_THRESHOLDS = (1, 5, 10, 50, 100)
TIER_REWARDS = (1, 2, 3, 4, 5)
MAX_LEVEL = 114
MIN_LEVEL = 1


@dataclass(frozen=True)
class TierProgress:
    reached_tier_index: int
    xp_delta: int


def highest_tier_index(msg_count: int) -> int:
    index = -1
    for i, threshold in enumerate(TIER_THRESHOLDS):
        if msg_count >= threshold:
            index = i
    return index


def tier_reward_by_index(index: int) -> int:
    if index < 0:
        return 0
    return TIER_REWARDS[index]


def calc_tier_progress(old_count: int, new_count: int, prev_highest_index: int) -> TierProgress:
    if new_count <= old_count:
        return TierProgress(reached_tier_index=prev_highest_index, xp_delta=0)

    new_highest = highest_tier_index(new_count)
    if new_highest <= prev_highest_index:
        return TierProgress(reached_tier_index=prev_highest_index, xp_delta=0)

    # "Only highest tier matters": grant the difference to top-up daily reward.
    old_reward = tier_reward_by_index(prev_highest_index)
    new_reward = tier_reward_by_index(new_highest)
    return TierProgress(reached_tier_index=new_highest, xp_delta=max(0, new_reward - old_reward))


def required_total_xp_for_level(level: int) -> int:
    bounded = max(MIN_LEVEL, min(MAX_LEVEL, level))
    return math.floor(0.2 * bounded * bounded + 18 * bounded)


def level_from_total_xp(total_xp: int) -> int:
    if total_xp <= 0:
        return MIN_LEVEL

    # Solve 0.2L^2 + 18L - xp <= 0 for maximum integer L.
    # 0.2 = 1/5 => L^2 + 90L - 5*xp <= 0
    a = 1.0
    b = 90.0
    c = -5.0 * float(total_xp)
    d = b * b - 4 * a * c
    root = (-b + math.sqrt(d)) / (2 * a)
    lv = int(math.floor(root))
    lv = max(MIN_LEVEL, min(MAX_LEVEL, lv))

    # Correct floating-point edge cases near exact thresholds.
    while lv < MAX_LEVEL and required_total_xp_for_level(lv + 1) <= total_xp:
        lv += 1
    while lv > MIN_LEVEL and required_total_xp_for_level(lv) > total_xp:
        lv -= 1

    return lv


def should_award_streak_bonus(streak_days: int) -> bool:
    return streak_days > 0 and streak_days % 7 == 0


def is_system_level_tag(tag: str | None) -> bool:
    if not tag:
        return True
    return tag.startswith("Lv.")


def build_level_tag(level: int) -> str:
    bounded = max(MIN_LEVEL, min(MAX_LEVEL, level))
    return f"Lv.{bounded}"
