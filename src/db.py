from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass
class UserState:
    chat_id: int
    user_id: int
    username: str | None
    display_name: str
    total_xp: int
    level: int
    streak_days: int
    last_qualified_date: str | None
    had_special_tag: int
    level_tag_synced_once: int


@dataclass
class DailyState:
    chat_id: int
    user_id: int
    biz_date: str
    msg_count: int
    highest_tier_awarded: int
    reached_10: int
    last_counted_ts: int


@dataclass(frozen=True)
class LevelTitleRule:
    start_level: int
    end_level: int
    title: str


class DB:
    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                display_name TEXT NOT NULL,
                total_xp INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 1,
                streak_days INTEGER NOT NULL DEFAULT 0,
                last_qualified_date TEXT,
                had_special_tag INTEGER NOT NULL DEFAULT 0,
                level_tag_synced_once INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY(chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS daily_stats (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                biz_date TEXT NOT NULL,
                msg_count INTEGER NOT NULL DEFAULT 0,
                highest_tier_awarded INTEGER NOT NULL DEFAULT -1,
                reached_10 INTEGER NOT NULL DEFAULT 0,
                last_counted_ts INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(chat_id, user_id, biz_date)
            );

            CREATE TABLE IF NOT EXISTS xp_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                biz_date TEXT NOT NULL,
                xp_delta INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS level_title_rules (
                chat_id INTEGER NOT NULL,
                start_level INTEGER NOT NULL,
                end_level INTEGER NOT NULL,
                title TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY(chat_id, start_level, end_level)
            );

            CREATE INDEX IF NOT EXISTS idx_users_chat_xp ON users(chat_id, total_xp DESC, user_id ASC);
            CREATE INDEX IF NOT EXISTS idx_daily_chat_date ON daily_stats(chat_id, biz_date, user_id);
            CREATE INDEX IF NOT EXISTS idx_xp_logs_chat_user ON xp_logs(chat_id, user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_lvtag_chat_range ON level_title_rules(chat_id, start_level, end_level);
            """
        )
        self._ensure_users_column("level_tag_synced_once", "INTEGER NOT NULL DEFAULT 0")
        self._conn.commit()

    def _ensure_users_column(self, column_name: str, definition_sql: str) -> None:
        cols = self._conn.execute("PRAGMA table_info(users)").fetchall()
        existing = {str(row[1]) for row in cols}
        if column_name in existing:
            return
        self._conn.execute(f"ALTER TABLE users ADD COLUMN {column_name} {definition_sql}")

    def upsert_level_title_rule(
        self,
        chat_id: int,
        start_level: int,
        end_level: int,
        title: str,
        now_ts: int,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO level_title_rules(chat_id, start_level, end_level, title, updated_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, start_level, end_level)
            DO UPDATE SET title=excluded.title, updated_at=excluded.updated_at
            """,
            (chat_id, start_level, end_level, title, now_ts),
        )
        self._conn.commit()

    def find_level_title(self, chat_id: int, level: int) -> str | None:
        row = self._conn.execute(
            """
            SELECT title
            FROM level_title_rules
            WHERE chat_id IN (?, 0)
              AND ? BETWEEN start_level AND end_level
            ORDER BY
              CASE WHEN chat_id = ? THEN 0 ELSE 1 END,
              (end_level - start_level) ASC,
              updated_at DESC
            LIMIT 1
            """,
            (chat_id, level, chat_id),
        ).fetchone()
        if not row:
            return None
        return str(row["title"])

    def get_or_create_user(
        self,
        chat_id: int,
        user_id: int,
        username: str | None,
        display_name: str,
        now_ts: int,
    ) -> UserState:
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO users(chat_id, user_id, username, display_name, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
              username=excluded.username,
              display_name=excluded.display_name,
              updated_at=excluded.updated_at
            """,
            (chat_id, user_id, username, display_name, now_ts, now_ts),
        )
        self._conn.commit()
        row = cur.execute(
            "SELECT * FROM users WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ).fetchone()
        return self._row_to_user(row)

    def get_or_create_daily(
        self,
        chat_id: int,
        user_id: int,
        biz_date: str,
    ) -> DailyState:
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO daily_stats(chat_id, user_id, biz_date)
            VALUES(?, ?, ?)
            ON CONFLICT(chat_id, user_id, biz_date) DO NOTHING
            """,
            (chat_id, user_id, biz_date),
        )
        self._conn.commit()
        row = cur.execute(
            "SELECT * FROM daily_stats WHERE chat_id=? AND user_id=? AND biz_date=?",
            (chat_id, user_id, biz_date),
        ).fetchone()
        return self._row_to_daily(row)

    def update_daily_state(
        self,
        chat_id: int,
        user_id: int,
        biz_date: str,
        msg_count: int,
        highest_tier_awarded: int,
        reached_10: int,
        last_counted_ts: int,
    ) -> None:
        self._conn.execute(
            """
            UPDATE daily_stats
            SET msg_count=?, highest_tier_awarded=?, reached_10=?, last_counted_ts=?
            WHERE chat_id=? AND user_id=? AND biz_date=?
            """,
            (msg_count, highest_tier_awarded, reached_10, last_counted_ts, chat_id, user_id, biz_date),
        )
        self._conn.commit()

    def apply_xp_and_level(
        self,
        chat_id: int,
        user_id: int,
        xp_delta: int,
        new_level: int,
        now_ts: int,
        biz_date: str,
        reason: str,
    ) -> None:
        if xp_delta <= 0:
            return
        self._conn.execute(
            """
            UPDATE users
            SET total_xp = total_xp + ?,
                level = CASE WHEN level > ? THEN level ELSE ? END,
                updated_at = ?
            WHERE chat_id=? AND user_id=?
            """,
            (xp_delta, new_level, new_level, now_ts, chat_id, user_id),
        )
        self._conn.execute(
            """
            INSERT INTO xp_logs(chat_id, user_id, biz_date, xp_delta, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (chat_id, user_id, biz_date, xp_delta, reason, now_ts),
        )
        self._conn.commit()

    def update_streak(self, chat_id: int, user_id: int, streak_days: int, qualified_date: str | None, now_ts: int) -> None:
        self._conn.execute(
            """
            UPDATE users
            SET streak_days=?, last_qualified_date=?, updated_at=?
            WHERE chat_id=? AND user_id=?
            """,
            (streak_days, qualified_date, now_ts, chat_id, user_id),
        )
        self._conn.commit()

    def mark_had_special_tag(self, chat_id: int, user_id: int, had_special_tag: bool, now_ts: int) -> None:
        self._conn.execute(
            """
            UPDATE users
            SET had_special_tag=?, updated_at=?
            WHERE chat_id=? AND user_id=?
            """,
            (1 if had_special_tag else 0, now_ts, chat_id, user_id),
        )
        self._conn.commit()

    def mark_level_tag_synced_once(self, chat_id: int, user_id: int, synced: bool, now_ts: int) -> None:
        self._conn.execute(
            """
            UPDATE users
            SET level_tag_synced_once=?, updated_at=?
            WHERE chat_id=? AND user_id=?
            """,
            (1 if synced else 0, now_ts, chat_id, user_id),
        )
        self._conn.commit()

    def get_user(self, chat_id: int, user_id: int) -> UserState | None:
        row = self._conn.execute(
            "SELECT * FROM users WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ).fetchone()
        if not row:
            return None
        return self._row_to_user(row)

    def rank_top_n(self, chat_id: int, n: int) -> list[sqlite3.Row]:
        cur = self._conn.cursor()
        return cur.execute(
            """
            SELECT user_id, username, display_name, level, total_xp,
                   ROW_NUMBER() OVER (ORDER BY total_xp DESC, user_id ASC) AS rank
            FROM users
            WHERE chat_id=?
            ORDER BY total_xp DESC, user_id ASC
            LIMIT ?
            """,
            (chat_id, n),
        ).fetchall()

    def rank_of_user(self, chat_id: int, user_id: int) -> sqlite3.Row | None:
        cur = self._conn.cursor()
        return cur.execute(
            """
            WITH ranked AS (
                SELECT user_id, username, display_name, level, total_xp,
                       ROW_NUMBER() OVER (ORDER BY total_xp DESC, user_id ASC) AS rank
                FROM users
                WHERE chat_id=?
            )
            SELECT * FROM ranked WHERE user_id=?
            """,
            (chat_id, user_id),
        ).fetchone()

    def _row_to_user(self, row: sqlite3.Row) -> UserState:
        return UserState(
            chat_id=int(row["chat_id"]),
            user_id=int(row["user_id"]),
            username=row["username"],
            display_name=row["display_name"],
            total_xp=int(row["total_xp"]),
            level=int(row["level"]),
            streak_days=int(row["streak_days"]),
            last_qualified_date=row["last_qualified_date"],
            had_special_tag=int(row["had_special_tag"]),
            level_tag_synced_once=int(row["level_tag_synced_once"]),
        )

    def _row_to_daily(self, row: sqlite3.Row) -> DailyState:
        return DailyState(
            chat_id=int(row["chat_id"]),
            user_id=int(row["user_id"]),
            biz_date=row["biz_date"],
            msg_count=int(row["msg_count"]),
            highest_tier_awarded=int(row["highest_tier_awarded"]),
            reached_10=int(row["reached_10"]),
            last_counted_ts=int(row["last_counted_ts"]),
        )


def row_to_display_name(row: sqlite3.Row | dict[str, Any]) -> str:
    username = row["username"] if isinstance(row, sqlite3.Row) else row.get("username")
    display_name = row["display_name"] if isinstance(row, sqlite3.Row) else row.get("display_name")
    if username:
        return f"@{username}"
    return str(display_name)
