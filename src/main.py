from __future__ import annotations

import argparse
import logging
import re
import time
from pathlib import Path
from typing import Iterable

from .config import load_settings
from .db import DB
from .rules import level_from_total_xp
from .service import XpService
from .telegram_api import TelegramAPI, TelegramAPIError
from .time_utils import biz_date_str, epoch_seconds


_HEADER_TOKENS = {
    "id",
    "user_id",
    "userid",
    "chat_id",
    "chatid",
    "xp",
    "score",
    "points",
    "amount",
    "积分",
    "积分数",
    "积分数量",
}


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram 群 XP 等级系统")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "-add",
        "--add",
        dest="add_file",
        help="批量加分文件路径，支持两列(user_id xp)或三列(chat_id user_id xp)",
    )
    mode.add_argument(
        "-del",
        "--del",
        dest="del_file",
        help="批量扣分文件路径，支持两列(user_id xp)或三列(chat_id user_id xp)",
    )
    parser.add_argument(
        "--chat-id",
        type=int,
        default=None,
        help="当导入文件使用两列格式时，指定统一的 chat_id",
    )
    parser.add_argument(
        "--reason",
        default="manual_import",
        help="写入 XP 日志的 reason 字段，默认 manual_import",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="导入文件编码，默认 utf-8",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅校验并预览，不写入数据库",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def _parse_integer_token(token: str, name: str, line_no: int) -> int:
    m = re.fullmatch(r"\[?(-?\d+)\]?", token.strip())
    if not m:
        raise ValueError(f"第 {line_no} 行 {name} 不是整数: {token}")
    return int(m.group(1))


def _is_header_like_tokens(tokens: list[str]) -> bool:
    if len(tokens) not in {2, 3}:
        return False
    normalized = [re.sub(r"[^\w\u4e00-\u9fff]", "", t).lower() for t in tokens]
    if not all(normalized):
        return False
    return all(t in _HEADER_TOKENS for t in normalized)


def _load_add_entries(file_path: Path, default_chat_id: int | None, encoding: str) -> list[tuple[int, int, int]]:
    if not file_path.exists() or not file_path.is_file():
        raise ValueError(f"导入文件不存在: {file_path}")

    entries: list[tuple[int, int, int]] = []
    errors: list[str] = []

    for line_no, raw_line in enumerate(file_path.read_text(encoding=encoding).splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        tokens = [t for t in re.split(r"[\s,]+", line) if t]
        if _is_header_like_tokens(tokens):
            continue
        try:
            if len(tokens) == 2:
                if default_chat_id is None:
                    raise ValueError(
                        f"第 {line_no} 行为两列格式，但未提供 --chat-id: {line}"
                    )
                chat_id = default_chat_id
                user_id = _parse_integer_token(tokens[0], "user_id", line_no)
                xp_delta = _parse_integer_token(tokens[1], "xp", line_no)
            elif len(tokens) == 3:
                chat_id = _parse_integer_token(tokens[0], "chat_id", line_no)
                user_id = _parse_integer_token(tokens[1], "user_id", line_no)
                xp_delta = _parse_integer_token(tokens[2], "xp", line_no)
            else:
                raise ValueError(
                    f"第 {line_no} 行格式错误，需两列(user_id xp)或三列(chat_id user_id xp): {line}"
                )

            if chat_id == 0:
                raise ValueError(f"第 {line_no} 行 chat_id 不能为 0")
            if user_id <= 0:
                raise ValueError(f"第 {line_no} 行 user_id 必须大于 0")
            if xp_delta <= 0:
                raise ValueError(f"第 {line_no} 行 xp 必须大于 0")

            entries.append((chat_id, user_id, xp_delta))
        except ValueError as exc:
            errors.append(str(exc))

    if errors:
        raise ValueError("\n".join(errors))
    if not entries:
        raise ValueError("导入文件没有可用数据")
    return entries


def _apply_entries(
    db: DB,
    entries: list[tuple[int, int, int]],
    reason: str,
    dry_run: bool,
    is_delete: bool,
) -> dict[str, int]:
    now_ts = epoch_seconds()
    biz_date = biz_date_str()

    summary = {
        "rows": len(entries),
        "total_xp": 0,
        "requested_total_xp": 0,
        "affected_users": 0,
        "created_users": 0,
        "leveled_up_users": 0,
        "leveled_down_users": 0,
        "skipped_users": 0,
    }
    seen_users: set[tuple[int, int]] = set()

    sign = -1 if is_delete else 1

    for chat_id, user_id, amount in entries:
        xp_delta = sign * amount
        summary["requested_total_xp"] += amount
        user = db.get_user(chat_id, user_id)
        if user is None:
            if is_delete:
                summary["skipped_users"] += 1
                continue

            summary["created_users"] += 1
            if not dry_run:
                db.get_or_create_user(
                    chat_id=chat_id,
                    user_id=user_id,
                    username=None,
                    display_name=f"user_{user_id}",
                    now_ts=now_ts,
                )
                user = db.get_user(chat_id, user_id)
            else:
                user = None

        old_level = user.level if user is not None else 1
        old_total_xp = user.total_xp if user is not None else 0
        target_total_xp = old_total_xp + xp_delta
        if target_total_xp < 0:
            target_total_xp = 0
        new_level = level_from_total_xp(target_total_xp)

        applied_delta = xp_delta
        if target_total_xp == old_total_xp:
            applied_delta = 0

        if not dry_run:
            applied_delta = db.apply_xp_delta_and_level(
                chat_id=chat_id,
                user_id=user_id,
                xp_delta=xp_delta,
                new_level=new_level,
                now_ts=now_ts,
                biz_date=biz_date,
                reason=reason,
            )

        if applied_delta == 0:
            continue

        summary["total_xp"] += applied_delta
        seen_users.add((chat_id, user_id))
        if new_level > old_level:
            summary["leveled_up_users"] += 1
        elif new_level < old_level:
            summary["leveled_down_users"] += 1

    summary["affected_users"] = len(seen_users)
    return summary


def _run_batch_import(args: argparse.Namespace) -> None:
    log_level = "INFO"
    db_path = "xp_bot.sqlite3"
    try:
        settings = load_settings()
        log_level = settings.log_level
        db_path = settings.db_path
    except ValueError:
        # BOT_TOKEN may be absent in offline import mode; keep env/default fallback.
        pass

    setup_logging(log_level)
    logger = logging.getLogger(__name__)

    is_delete = bool(args.del_file)
    input_file = args.del_file if is_delete else args.add_file
    action_text = "del" if is_delete else "add"

    try:
        entries = _load_add_entries(
            file_path=Path(input_file),
            default_chat_id=args.chat_id,
            encoding=args.encoding,
        )

        db = DB(db_path)
        db.init_schema()

        reason = args.reason
        if reason == "manual_import":
            reason = "manual_deduct" if is_delete else "manual_import"

        summary = _apply_entries(
            db,
            entries,
            reason=reason,
            dry_run=bool(args.dry_run),
            is_delete=is_delete,
        )
    except UnicodeDecodeError as exc:
        logger.error("批量%s失败：文件编码不匹配 (%s)。可尝试 --encoding gbk", action_text, exc)
        raise SystemExit(2)
    except ValueError as exc:
        logger.error("批量%s失败：\n%s", action_text, exc)
        logger.error("示例(两列): 12345678 10  (需配合 --chat-id)")
        logger.error("示例(三列): -1001234567890 12345678 10")
        raise SystemExit(2)

    mode_text = "dry-run" if args.dry_run else "applied"
    logger.info(
        "Batch %s %s: rows=%s users=%s created=%s skipped=%s leveled_up=%s leveled_down=%s requested_xp=%s applied_xp=%s reason=%s db=%s",
        action_text,
        mode_text,
        summary["rows"],
        summary["affected_users"],
        summary["created_users"],
        summary["skipped_users"],
        summary["leveled_up_users"],
        summary["leveled_down_users"],
        summary["requested_total_xp"],
        summary["total_xp"],
        reason,
        db_path,
    )


def run() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    db = DB(settings.db_path)
    db.init_schema()

    tg = TelegramAPI(settings.bot_token)
    service = XpService(db, tg, top_n=settings.top_n, owner_id=settings.owner_id)

    logger = logging.getLogger(__name__)
    logger.info("Bot started with long polling")

    offset: int | None = None
    while True:
        try:
            updates = tg.get_updates(offset=offset, timeout=settings.poll_timeout)
            for update in updates:
                update_id = int(update.get("update_id", 0))
                if update_id > 0:
                    offset = update_id + 1
                service.handle_update(update)
        except TelegramAPIError as exc:
            logger.warning("Telegram API error: %s", exc)
            time.sleep(2)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
        except Exception:
            logger.exception("Unhandled error in main loop")
            time.sleep(2)


if __name__ == "__main__":
    cli_args = _parse_args()
    if cli_args.add_file or cli_args.del_file:
        _run_batch_import(cli_args)
    else:
        run()
