from __future__ import annotations

import unittest
from unittest.mock import Mock

from src.db import DB
from src.service import XpService


class ServiceTagSyncTests(unittest.TestCase):
    def test_regular_message_sets_level_tag_when_missing(self) -> None:
        db = DB(":memory:")
        db.init_schema()

        tg = Mock()
        tg.get_chat_member.return_value = {"status": "member", "tag": ""}
        tg.set_chat_member_tag.return_value = True

        service = XpService(db=db, tg=tg, top_n=10)

        update = {
            "message": {
                "chat": {"id": 1001, "type": "supergroup"},
                "from": {"id": 42, "username": "alice", "first_name": "Alice"},
                "text": "hello",
            }
        }

        service.handle_update(update)

        tg.get_chat_member.assert_called_once_with(1001, 42)
        tg.set_chat_member_tag.assert_called_once_with(1001, 42, "Lv.1")

    def test_skip_tag_check_after_synced_once(self) -> None:
        db = DB(":memory:")
        db.init_schema()

        tg = Mock()
        tg.get_chat_member.return_value = {"status": "member", "tag": ""}
        tg.set_chat_member_tag.return_value = True

        service = XpService(db=db, tg=tg, top_n=10)

        update = {
            "message": {
                "chat": {"id": 1001, "type": "supergroup"},
                "from": {"id": 42, "username": "alice", "first_name": "Alice"},
                "text": "hello",
            }
        }

        service.handle_update(update)
        service.handle_update(update)

        tg.get_chat_member.assert_called_once_with(1001, 42)
        tg.set_chat_member_tag.assert_called_once_with(1001, 42, "Lv.1")


if __name__ == "__main__":
    unittest.main()
