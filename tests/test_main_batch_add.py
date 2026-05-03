from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.db import DB
from src.main import _apply_add_entries, _load_add_entries


class MainBatchAddTests(unittest.TestCase):
    def test_load_add_entries_with_default_chat_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "batch.txt"
            p.write_text("# comment\n[101] [5]\n202 8\n", encoding="utf-8")

            rows = _load_add_entries(p, default_chat_id=-10001, encoding="utf-8")
            self.assertEqual(rows, [(-10001, 101, 5), (-10001, 202, 8)])

    def test_load_add_entries_with_explicit_chat_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "batch.txt"
            p.write_text("-10001 101 5\n-10001,202,9\n", encoding="utf-8")

            rows = _load_add_entries(p, default_chat_id=None, encoding="utf-8")
            self.assertEqual(rows, [(-10001, 101, 5), (-10001, 202, 9)])

    def test_load_add_entries_requires_chat_id_for_two_columns(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "batch.txt"
            p.write_text("101 5\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                _load_add_entries(p, default_chat_id=None, encoding="utf-8")

    def test_apply_add_entries_updates_xp_and_level(self) -> None:
        db = DB(":memory:")
        db.init_schema()

        # Create a user first so we can verify incremental updates.
        db.get_or_create_user(
            chat_id=-10001,
            user_id=101,
            username="alice",
            display_name="Alice",
            now_ts=0,
        )

        summary = _apply_add_entries(
            db,
            entries=[(-10001, 101, 10), (-10001, 202, 8)],
            reason="manual_import",
            dry_run=False,
        )

        self.assertEqual(summary["rows"], 2)
        self.assertEqual(summary["affected_users"], 2)
        self.assertEqual(summary["created_users"], 1)
        self.assertEqual(summary["total_xp"], 18)

        user1 = db.get_user(-10001, 101)
        user2 = db.get_user(-10001, 202)
        self.assertIsNotNone(user1)
        self.assertIsNotNone(user2)
        self.assertEqual(user1.total_xp, 10)
        self.assertEqual(user2.total_xp, 8)


if __name__ == "__main__":
    unittest.main()
