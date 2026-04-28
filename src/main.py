from __future__ import annotations

import logging
import time

from .config import load_settings
from .db import DB
from .service import XpService
from .telegram_api import TelegramAPI, TelegramAPIError


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
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
    run()
