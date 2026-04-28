from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from .db import DB, row_to_display_name
from .rules import (
    build_level_tag,
    calc_tier_progress,
    is_system_level_tag,
    level_from_total_xp,
    required_total_xp_for_level,
    should_award_streak_bonus,
)
from .telegram_api import TelegramAPI, TelegramAPIError
from .time_utils import UTC8, biz_date_str, epoch_seconds


class XpService:
    def __init__(self, db: DB, tg: TelegramAPI, top_n: int, owner_id: int | None = None) -> None:
        self._db = db
        self._tg = tg
        self._top_n = top_n
        self._owner_id = owner_id
        self._logger = logging.getLogger(__name__)

    def handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message")
        if not message:
            return

        text = message.get("text")
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        chat_type = chat.get("type")

        if chat_id is None:
            return

        if not isinstance(text, str) or not text.strip():
            return

        if text.startswith("/"):
            self._handle_command(chat_id=int(chat_id), message=message, text=text)
            return

        if chat_type not in {"group", "supergroup"}:
            return

        self._handle_regular_message(chat_id=int(chat_id), message=message)

    def _handle_command(self, chat_id: int, message: dict[str, Any], text: str) -> None:
        cmd = text.split()[0].split("@")[0].strip().lower()
        chat_type = str((message.get("chat") or {}).get("type", ""))
        from_user = message.get("from") or {}
        caller_id = int(from_user.get("id", 0)) if from_user.get("id") else 0
        reply_to_message_id = int(message.get("message_id", 0)) if message.get("message_id") else None

        if cmd == "/setlvtag":
            self._handle_setlvtag(chat_id, chat_type, caller_id, text, reply_to_message_id)
            return

        if cmd == "/my":
            if chat_type not in {"group", "supergroup"}:
                self._tg.send_message(chat_id, "请在群内使用 /my。", reply_to_message_id=reply_to_message_id)
                return
            if caller_id <= 0:
                return
            output = self._render_my(chat_id, caller_id)
            self._tg.send_message(chat_id, output, reply_to_message_id=reply_to_message_id)
            return

        if cmd == "/rank":
            if chat_type not in {"group", "supergroup"}:
                return
            if caller_id <= 0:
                return
            output = self._render_rank(chat_id, caller_id)
            self._tg.send_message(chat_id, output, reply_to_message_id=reply_to_message_id)

    def _render_rank(self, chat_id: int, caller_id: int) -> str:
        rows = self._db.rank_top_n(chat_id, self._top_n)
        if not rows:
            return "本群暂无数据。"

        lines: list[str] = [f"本群排行榜 Top {self._top_n}"]
        in_top = False
        for row in rows:
            rank = int(row["rank"])
            uid = int(row["user_id"])
            name = row_to_display_name(row)
            level = int(row["level"])
            xp = int(row["total_xp"])
            title = self._db.find_level_title(chat_id, level)
            level_part = f"Lv.{level}"
            if title:
                level_part = f"Lv.{level} | [{title}]"
            lines.append(f"{rank}. {name} | {level_part} | {xp} XP")
            if uid == caller_id:
                in_top = True

        if not in_top:
            self_row = self._db.rank_of_user(chat_id, caller_id)
            if self_row:
                lines.append("---")
                rank = int(self_row["rank"])
                name = row_to_display_name(self_row)
                level = int(self_row["level"])
                xp = int(self_row["total_xp"])
                title = self._db.find_level_title(chat_id, level)
                level_part = f"Lv.{level}"
                if title:
                    level_part = f"Lv.{level} | [{title}]"
                lines.append(f"你的排名: {rank}. {name} | {level_part} | {xp} XP")

        return "\n".join(lines)

    def _render_my(self, chat_id: int, user_id: int) -> str:
        user = self._db.get_user(chat_id, user_id)
        if not user:
            return "你在本群还没有活跃记录。"

        current_level = int(user.level)
        current_xp = int(user.total_xp)

        title = self._db.find_level_title(chat_id, current_level)
        level_part = f"Lv.{current_level}"
        if title:
            level_part = f"Lv.{current_level} | [{title}]"

        if current_level >= 114:
            bar = self._progress_bar(1.0)
            return "\n".join(
                [
                    "个人信息",
                    f"等级: {level_part}",
                    f"当前XP: {current_xp}",
                    "距离下一级: 已满级",
                    f"进度: {bar} 100%",
                ]
            )

        level_floor_xp = required_total_xp_for_level(current_level)
        next_level_xp = required_total_xp_for_level(current_level + 1)
        span = max(1, next_level_xp - level_floor_xp)
        done = max(0, current_xp - level_floor_xp)
        ratio = min(1.0, max(0.0, done / span))
        remain = max(0, next_level_xp - current_xp)
        percent = int(round(ratio * 100))
        bar = self._progress_bar(ratio)

        return "\n".join(
            [
                "个人信息",
                f"等级: {level_part}",
                f"当前XP: {current_xp}",
                f"距离下一级: {remain} XP",
                f"进度: {bar} {percent}%",
            ]
        )

    def _progress_bar(self, ratio: float, width: int = 20) -> str:
        bounded = min(1.0, max(0.0, ratio))
        filled = int(round(width * bounded))
        empty = max(0, width - filled)
        return "[" + ("#" * filled) + ("-" * empty) + "]"

    def _handle_setlvtag(
        self,
        chat_id: int,
        chat_type: str,
        caller_id: int,
        text: str,
        reply_to_message_id: int | None,
    ) -> None:
        if caller_id <= 0:
            return

        rules = self._parse_setlvtag_rules(text)
        if not rules:
            self._tg.send_message(
                chat_id,
                "格式错误。示例: /setlvtag 1-10 [新手] 11-20 [进阶]",
                reply_to_message_id=reply_to_message_id,
            )
            return

        target_chat_id = chat_id
        if chat_type == "private":
            if self._owner_id is None or caller_id != self._owner_id:
                self._tg.send_message(
                    chat_id,
                    "私聊设置需要 OWNER_ID 且仅限机器人所有者。",
                    reply_to_message_id=reply_to_message_id,
                )
                return
            target_chat_id = 0
        elif chat_type in {"group", "supergroup"}:
            try:
                member = self._tg.get_chat_member(chat_id, caller_id)
            except TelegramAPIError:
                self._tg.send_message(
                    chat_id,
                    "无法校验管理员权限，请稍后再试。",
                    reply_to_message_id=reply_to_message_id,
                )
                return

            status = str(member.get("status", ""))
            if status not in {"creator", "administrator"}:
                self._tg.send_message(
                    chat_id,
                    "仅群管理员可设置等级头衔。",
                    reply_to_message_id=reply_to_message_id,
                )
                return
        else:
            return

        now_ts = epoch_seconds()
        for start_level, end_level, title in rules:
            self._db.upsert_level_title_rule(
                chat_id=target_chat_id,
                start_level=start_level,
                end_level=end_level,
                title=title,
                now_ts=now_ts,
            )

        scope_text = "全局默认" if target_chat_id == 0 else "当前群"
        self._tg.send_message(
            chat_id,
            f"已更新{scope_text}等级头衔，共 {len(rules)} 条。",
            reply_to_message_id=reply_to_message_id,
        )

    def _parse_setlvtag_rules(self, text: str) -> list[tuple[int, int, str]]:
        body = text.split(" ", 1)
        if len(body) < 2:
            return []

        args = body[1].strip()
        # Format: 1-10 [Title] 11-20 [Another Title]
        pattern = re.compile(r"(\d{1,3})\s*-\s*(\d{1,3})\s*\[([^\[\]]+)\]")
        matches = list(pattern.finditer(args))
        if not matches:
            return []

        # Ensure the full input is covered by valid segments + spaces.
        normalized = pattern.sub("", args)
        if normalized.strip():
            return []

        rules: list[tuple[int, int, str]] = []
        for m in matches:
            start_level = int(m.group(1))
            end_level = int(m.group(2))
            title = m.group(3).strip()
            if not title:
                return []
            if start_level < 1 or end_level > 114 or start_level > end_level:
                return []
            rules.append((start_level, end_level, title))

        return rules

    def _handle_regular_message(self, chat_id: int, message: dict[str, Any]) -> None:
        from_user = message.get("from") or {}
        user_id = from_user.get("id")
        if user_id is None:
            return

        user_id = int(user_id)
        username = from_user.get("username")
        display_name = self._display_name(from_user)
        now_ts = epoch_seconds()
        biz_date = biz_date_str()

        user = self._db.get_or_create_user(chat_id, user_id, username, display_name, now_ts)
        daily = self._db.get_or_create_daily(chat_id, user_id, biz_date)

        # 5-second merge only affects XP counting.
        if daily.last_counted_ts > 0 and now_ts - daily.last_counted_ts < 5:
            if not bool(user.level_tag_synced_once):
                self._sync_level_tag(chat_id, user_id, user.level)
            return

        old_count = daily.msg_count
        new_count = old_count + 1
        progress = calc_tier_progress(old_count, new_count, daily.highest_tier_awarded)
        reached_10 = daily.reached_10

        self._db.update_daily_state(
            chat_id=chat_id,
            user_id=user_id,
            biz_date=biz_date,
            msg_count=new_count,
            highest_tier_awarded=progress.reached_tier_index,
            reached_10=reached_10,
            last_counted_ts=now_ts,
        )

        user = self._db.get_user(chat_id, user_id)
        if not user:
            return

        leveled_up = False

        if progress.xp_delta > 0:
            target_level = level_from_total_xp(user.total_xp + progress.xp_delta)
            leveled_up = target_level > user.level
            self._db.apply_xp_and_level(
                chat_id=chat_id,
                user_id=user_id,
                xp_delta=progress.xp_delta,
                new_level=target_level,
                now_ts=now_ts,
                biz_date=biz_date,
                reason="daily_tier",
            )
            user = self._db.get_user(chat_id, user_id)
            if not user:
                return

        # Streak rule: first time reaching 10 messages today.
        if new_count >= 10 and reached_10 == 0:
            streak_days = self._next_streak_days(user.last_qualified_date, biz_date, user.streak_days)
            self._db.update_daily_state(
                chat_id=chat_id,
                user_id=user_id,
                biz_date=biz_date,
                msg_count=new_count,
                highest_tier_awarded=progress.reached_tier_index,
                reached_10=1,
                last_counted_ts=now_ts,
            )
            self._db.update_streak(chat_id, user_id, streak_days, biz_date, now_ts)
            user = self._db.get_user(chat_id, user_id)
            if not user:
                return

            if should_award_streak_bonus(streak_days):
                bonus = 5
                target_level = level_from_total_xp(user.total_xp + bonus)
                leveled_up = leveled_up or target_level > user.level
                self._db.apply_xp_and_level(
                    chat_id=chat_id,
                    user_id=user_id,
                    xp_delta=bonus,
                    new_level=target_level,
                    now_ts=now_ts,
                    biz_date=biz_date,
                    reason="streak_7d",
                )
                user = self._db.get_user(chat_id, user_id)
                if not user:
                    return

        # Once synced once for a user, skip all future checks.
        if not bool(user.level_tag_synced_once):
            self._sync_level_tag(chat_id, user_id, user.level)

    def _sync_level_tag(self, chat_id: int, user_id: int, level: int) -> None:
        now_ts = epoch_seconds()
        try:
            member = self._tg.get_chat_member(chat_id, user_id)
        except TelegramAPIError as exc:
            self._logger.warning("getChatMember failed for %s/%s: %s", chat_id, user_id, exc)
            return

        status = str(member.get("status", ""))
        if status in {"creator", "administrator"}:
            # Do not override admin related labels.
            return

        current_tag = member.get("tag")
        if not isinstance(current_tag, str):
            current_tag = ""

        if not is_system_level_tag(current_tag):
            self._db.mark_had_special_tag(chat_id, user_id, True, now_ts)
            return

        target_tag = build_level_tag(level)
        if current_tag == target_tag:
            self._db.mark_level_tag_synced_once(chat_id, user_id, True, now_ts)
            self._db.mark_had_special_tag(chat_id, user_id, False, now_ts)
            return

        try:
            self._tg.set_chat_member_tag(chat_id, user_id, target_tag)
            self._db.mark_level_tag_synced_once(chat_id, user_id, True, now_ts)
            self._db.mark_had_special_tag(chat_id, user_id, False, now_ts)
        except (TelegramAPIError, ValueError) as exc:
            self._logger.warning("setChatMemberTag failed for %s/%s: %s", chat_id, user_id, exc)

    def _next_streak_days(self, last_qualified_date: str | None, current_date: str, current_streak: int) -> int:
        if not last_qualified_date:
            return 1

        try:
            prev = datetime.strptime(last_qualified_date, "%Y-%m-%d").replace(tzinfo=UTC8)
            curr = datetime.strptime(current_date, "%Y-%m-%d").replace(tzinfo=UTC8)
        except ValueError:
            return 1

        diff = (curr.date() - prev.date()).days
        if diff == 1:
            return current_streak + 1
        if diff == 0:
            return current_streak
        return 1

    def _display_name(self, from_user: dict[str, Any]) -> str:
        first = str(from_user.get("first_name") or "").strip()
        last = str(from_user.get("last_name") or "").strip()
        full = (first + " " + last).strip()
        if full:
            return full
        username = str(from_user.get("username") or "").strip()
        if username:
            return "@" + username
        return f"user_{from_user.get('id', 'unknown')}"
