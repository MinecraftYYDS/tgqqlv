from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    bot_token: str
    top_n: int = 10
    poll_timeout: int = 30
    log_level: str = "INFO"
    db_path: str = "xp_bot.sqlite3"
    owner_id: int | None = None


_DOTENV_LOADED = False


def _load_dotenv_if_needed() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return

    # Prefer current working directory, then project root as fallback.
    candidates = [Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"]
    seen: set[Path] = set()
    for env_path in candidates:
        resolved = env_path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if not env_path.exists() or not env_path.is_file():
            continue

        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue

            parsed = value.strip()
            if len(parsed) >= 2 and parsed[0] == parsed[-1] and parsed[0] in {"\"", "'"}:
                parsed = parsed[1:-1]
            os.environ[key] = parsed

    _DOTENV_LOADED = True


def load_settings() -> Settings:
    _load_dotenv_if_needed()

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
