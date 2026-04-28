from __future__ import annotations

import unittest
from unittest.mock import Mock

from src.db import DB
from src.rules import (
    build_level_tag,
    calc_tier_progress,
    is_system_level_tag,
    level_from_total_xp,
    required_total_xp_for_level,
    should_award_streak_bonus,
)
from src.service import XpService


class RulesTests(unittest.TestCase):
    def test_tier_progress_top_up(self) -> None:
        p1 = calc_tier_progress(old_count=0, new_count=1, prev_highest_index=-1)
        self.assertEqual(p1.reached_tier_index, 0)
        self.assertEqual(p1.xp_delta, 1)

        p2 = calc_tier_progress(old_count=1, new_count=5, prev_highest_index=0)
        self.assertEqual(p2.reached_tier_index, 1)
        self.assertEqual(p2.xp_delta, 1)

        p3 = calc_tier_progress(old_count=50, new_count=100, prev_highest_index=3)
        self.assertEqual(p3.reached_tier_index, 4)
        self.assertEqual(p3.xp_delta, 1)

    def test_level_curve_roundtrip(self) -> None:
        for level in (1, 10, 25, 50, 100, 114):
            xp = required_total_xp_for_level(level)
            resolved = level_from_total_xp(xp)
            self.assertGreaterEqual(resolved, level)

    def test_streak_bonus(self) -> None:
        self.assertFalse(should_award_streak_bonus(6))
        self.assertTrue(should_award_streak_bonus(7))
        self.assertFalse(should_award_streak_bonus(13))
        self.assertTrue(should_award_streak_bonus(14))

    def test_tag_policy(self) -> None:
        self.assertTrue(is_system_level_tag(""))
        self.assertTrue(is_system_level_tag("Lv.12"))
        self.assertFalse(is_system_level_tag("VIP"))
        self.assertEqual(build_level_tag(25), "Lv.25")

    def test_setlvtag_parser(self) -> None:
        db = DB(":memory:")
        db.init_schema()
        service = XpService(db=db, tg=Mock(), top_n=10)

        parsed = service._parse_setlvtag_rules("/setlvtag 1-10 [新手] 11-20 [进阶]")
        self.assertEqual(parsed, [(1, 10, "新手"), (11, 20, "进阶")])

        invalid = service._parse_setlvtag_rules("/setlvtag 1-10 新手")
        self.assertEqual(invalid, [])

    def test_progress_bar_render(self) -> None:
        db = DB(":memory:")
        db.init_schema()
        service = XpService(db=db, tg=Mock(), top_n=10)

        self.assertEqual(service._progress_bar(0.0, width=10), "[----------]")
        self.assertEqual(service._progress_bar(0.5, width=10), "[#####-----]")
        self.assertEqual(service._progress_bar(1.0, width=10), "[##########]")


if __name__ == "__main__":
    unittest.main()
