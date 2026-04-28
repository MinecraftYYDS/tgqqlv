from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

UTC8 = timezone(timedelta(hours=8))


def now_utc() -> datetime:
    return datetime.now(UTC)


def now_utc8() -> datetime:
    return now_utc().astimezone(UTC8)


def biz_date_str(dt: datetime | None = None) -> str:
    target = dt.astimezone(UTC8) if dt else now_utc8()
    return target.strftime("%Y-%m-%d")


def epoch_seconds(dt: datetime | None = None) -> int:
    target = dt if dt else now_utc()
    return int(target.timestamp())
