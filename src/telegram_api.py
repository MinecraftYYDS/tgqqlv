from __future__ import annotations

import logging
from typing import Any

import requests


class TelegramAPIError(Exception):
    pass


class TelegramAPI:
    def __init__(self, token: str) -> None:
        self._logger = logging.getLogger(__name__)
        self._base = f"https://api.telegram.org/bot{token}"
        self._session = requests.Session()

    def _call(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        timeout: float | tuple[float, float] = 20,
    ) -> Any:
        url = f"{self._base}/{method}"
        try:
            response = self._session.post(url, json=payload or {}, timeout=timeout)
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            raise TelegramAPIError(f"{method} request failed: {exc}") from exc
        if not body.get("ok"):
            description = body.get("description", "Unknown Telegram API error")
            error_code = body.get("error_code")
            raise TelegramAPIError(f"{method} failed ({error_code}): {description}")
        return body.get("result")

    def get_updates(self, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        # Long polling timeout on Telegram side should be smaller than HTTP read timeout.
        request_timeout = (10.0, float(max(timeout + 10, 30)))
        result = self._call("getUpdates", payload, timeout=request_timeout)
        return result if isinstance(result, list) else []

    def send_message(self, chat_id: int, text: str) -> None:
        self._call("sendMessage", {"chat_id": chat_id, "text": text})

    def get_chat_member(self, chat_id: int, user_id: int) -> dict[str, Any]:
        result = self._call("getChatMember", {"chat_id": chat_id, "user_id": user_id})
        return result if isinstance(result, dict) else {}

    def set_chat_member_tag(self, chat_id: int, user_id: int, tag: str) -> bool:
        # Telegram docs via GramIO: tag max 16 and no emoji.
        if len(tag) > 16:
            raise ValueError("tag length must be <= 16")
        result = self._call("setChatMemberTag", {"chat_id": chat_id, "user_id": user_id, "tag": tag})
        return bool(result)
