import csv
import io
import re
from collections import Counter

from aiogram import Bot
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramNotFound,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardMarkup, Message

from src.config import Config
from src.models import Event, Registration, User


def is_valid_event_code(code: str) -> bool:
    return bool(re.match(r"^[a-z0-9_]+$", code)) and len(code) <= 64


def suggest_event_code(title: str) -> str:
    code = title.lower().strip()
    code = re.sub(r"[^a-z0-9\s-]", "", code)
    code = re.sub(r"[-\s]+", "_", code)
    code = code.strip("_")
    if not code:
        import hashlib

        code = hashlib.md5(title.encode()).hexdigest()[:12]  # noqa: S324
    return code[:50]


def get_or_create_user(tg_user) -> User:  # noqa: ANN001
    user, _ = User.get_or_create(
        telegram_id=tg_user.id,
        defaults={
            "username": tg_user.username,
            "first_name": tg_user.first_name,
            "last_name": tg_user.last_name,
        },
    )
    return user


def get_event_message(event: Event, key: str, config: Config) -> str:
    event_msg = getattr(event, f"msg_{key}", None)
    if event_msg:
        return event_msg
    return getattr(config.event_defaults, key)


def generate_event_csv(event: Event) -> io.StringIO:
    registrations = (
        Registration.select()
        .where(
            Registration.event == event,
            Registration.cancelled == False,  # noqa: E712
        )
        .join(User)
    )

    output = io.StringIO()
    writer = csv.writer(output)

    headers = ["telegram_id", "username", "first_name", "last_name", "registered_at"]
    if event.custom_question:
        headers.append("answer")
    writer.writerow(headers)

    for reg in registrations:
        # Handle both datetime objects and strings (SQLite stores as string)
        registered_at = reg.registered_at
        if hasattr(registered_at, "isoformat"):
            registered_at = registered_at.isoformat()
        row = [
            reg.user.telegram_id,
            reg.user.username or "",
            reg.user.first_name or "",
            reg.user.last_name or "",
            registered_at,
        ]
        if event.custom_question:
            row.append(reg.answer or "")
        writer.writerow(row)

    output.seek(0)
    return output


async def send_broadcast_messages(
    bot: Bot,
    registrations,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
    delay: float = 0.05,
    progress_callback=None,
    progress_interval: int = 5,
) -> tuple[int, int, Counter]:
    """Send broadcast messages and return (sent, failed, failure_reasons).

    failure_reasons is a Counter with keys like 'blocked', 'deactivated', 'not_found', 'other'.
    """
    import asyncio

    sent = 0
    failed = 0
    failure_reasons: Counter = Counter()
    total = len(registrations)
    last_progress = 0

    for i, reg in enumerate(registrations):
        try:
            await bot.send_message(
                reg.user.telegram_id,
                text,
                reply_markup=keyboard,
            )
            sent += 1
        except TelegramForbiddenError as e:
            failed += 1
            msg = str(e).lower()
            if "blocked" in msg:
                failure_reasons["blocked"] += 1
            elif "deactivated" in msg:
                failure_reasons["deactivated"] += 1
            elif "kicked" in msg:
                failure_reasons["kicked"] += 1
            else:
                failure_reasons["forbidden"] += 1
        except TelegramNotFound:
            failed += 1
            failure_reasons["not_found"] += 1
        except TelegramRetryAfter as e:
            failed += 1
            failure_reasons[f"rate_limited ({e.retry_after}s)"] += 1
        except Exception:
            failed += 1
            failure_reasons["other"] += 1

        processed = i + 1
        if progress_callback and (processed - last_progress) >= progress_interval:
            try:
                await progress_callback(sent, failed, total, processed)
                last_progress = processed
            except Exception:
                pass  # Don't let progress update failures stop the broadcast

        if delay > 0:
            await asyncio.sleep(delay)

    return sent, failed, failure_reasons


def format_failure_reasons(failure_reasons: Counter) -> str:
    if not failure_reasons:
        return ""
    parts = [f"{count} {reason}" for reason, count in failure_reasons.most_common()]
    return f" ({', '.join(parts)})"


def format_broadcast_progress(
    sent: int, failed: int, total: int, processed: int
) -> str:
    pct = int(processed / total * 100) if total > 0 else 0
    bar_filled = pct // 10
    bar_empty = 10 - bar_filled
    bar = "▓" * bar_filled + "░" * bar_empty
    return f"📤 *Sending...*\n\n{bar} {pct}%\n{processed}/{total} processed"


def get_event_stats(event: Event) -> dict:
    total = Registration.select().where(Registration.event == event).count()
    active = (
        Registration.select()
        .where(
            Registration.event == event,
            Registration.cancelled == False,  # noqa: E712
        )
        .count()
    )
    confirmed = (
        Registration.select()
        .where(
            Registration.event == event,
            Registration.cancelled == False,  # noqa: E712
            Registration.confirmed == True,  # noqa: E712
        )
        .count()
    )
    cancelled = total - active
    pending = active - confirmed

    return {
        "registered": active,
        "confirmed": confirmed,
        "cancelled": cancelled,
        "pending": pending,
    }


def admin_check(config: Config):  # noqa: ANN201
    async def check(message: Message) -> bool:  # noqa: RUF029
        return config.is_admin_context(message.chat.id, message.from_user.id)

    return check
