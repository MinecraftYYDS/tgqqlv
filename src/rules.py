from __future__ import annotations

import math
from dataclasses import dataclass

TIER_THRESHOLDS = (1, 5, 10, 50, 100)
TIER_REWARDS = (1, 2, 3, 4, 5)
MAX_LEVEL = 114
MIN_LEVEL = 1
MAX_DAILY_XP = 5
STREAK_BONUS_XP = 5
STREAK_PERIOD_DAYS = 7


def full_active_xp_per_day() -> float:
    # Full active assumption:
    # - Daily tier max: +5 XP
    # - Streak bonus average: +5 / 7 XP per day
    return MAX_DAILY_XP + (STREAK_BONUS_XP / STREAK_PERIOD_DAYS)


def target_days_for_level(level: int) -> float:
    # User requested pace:
    # Lv.10 -> 15 days, Lv.20 -> 20 days, and so on.
    # This implies +5 days per +10 levels.
    bounded = max(MIN_LEVEL, min(MAX_LEVEL, level))
    return 10.0 + (bounded / 2.0)


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
    days = target_days_for_level(level)
    return int(math.ceil(days * full_active_xp_per_day()))


def level_from_total_xp(total_xp: int) -> int:
    if total_xp <= 0:
        return MIN_LEVEL

    low = MIN_LEVEL
    high = MAX_LEVEL
    ans = MIN_LEVEL

    while low <= high:
        mid = (low + high) // 2
        need = required_total_xp_for_level(mid)
        if need <= total_xp:
            ans = mid
            low = mid + 1
        else:
            high = mid - 1

    return ans


def should_award_streak_bonus(streak_days: int) -> bool:
    return streak_days > 0 and streak_days % 7 == 0


def is_system_level_tag(tag: str | None) -> bool:
    if not tag:
        return True
    return tag.startswith("Lv.")


def build_level_tag(level: int) -> str:
    bounded = max(MIN_LEVEL, min(MAX_LEVEL, level))
    return f"Lv.{bounded}"
