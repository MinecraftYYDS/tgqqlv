from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    top_n: int = 10
    poll_timeout: int = 30
    log_level: str = "INFO"
    db_path: str = "xp_bot.sqlite3"
    owner_id: int | None = None


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("BOT_TOKEN is required")

    top_n = int(os.getenv("TOP_N", "10"))
    poll_timeout = int(os.getenv("POLL_TIMEOUT", "30"))
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    db_path = os.getenv("DB_PATH", "xp_bot.sqlite3").strip()
    owner_raw = os.getenv("OWNER_ID", "").strip()
    owner_id = int(owner_raw) if owner_raw else None

    return Settings(
        bot_token=token,
        top_n=top_n,
        poll_timeout=poll_timeout,
        log_level=log_level,
        db_path=db_path,
        owner_id=owner_id,
    )
