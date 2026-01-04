from aiogram import F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.config import Config
from src.models import Event
from src.visualization import generate_and_upload_visualization

from . import router


@router.message(Command("visualize"))
async def cmd_visualize(message: Message, config: Config) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    args = message.text.split()[1:] if message.text else []
    local_mode = "local" in args

    active_event = Event.get_active()
    archived_events = list(
        Event.select()
        .where(Event.is_active == False)  # noqa: E712
        .order_by(Event.archived_at.desc())
        .limit(10)
    )

    if not active_event and not archived_events:
        await message.answer(config.visualization.no_events)
        return

    mode = "local" if local_mode else "remote"
    buttons = []
    if active_event:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"📌 {active_event.title} (Active)",
                    callback_data=f"visualize:{mode}:{active_event.id}",
                )
            ]
        )

    for i, event in enumerate(archived_events, 1):
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{i}. {event.title}",
                    callback_data=f"visualize:{mode}:{event.id}",
                )
            ]
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        "📊 *Generate Visualization*\n\nSelect an event:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("visualize:"))
async def handle_visualize_event(callback: CallbackQuery, config: Config) -> None:
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    parts = callback.data.split(":")
    mode = parts[1]
    event_id = int(parts[2])
    local_mode = mode == "local"

    event = Event.get_or_none(Event.id == event_id)
    if not event:
        await callback.answer("Event not found")
        return

    await callback.message.edit_text(config.visualization.generating)

    try:
        result, is_remote = generate_and_upload_visualization(event, local=local_mode)
        if is_remote:
            msg = config.visualization.success.format(url=result)
        else:
            msg = config.visualization.local_success.format(path=result)
        await callback.message.edit_text(msg, parse_mode="Markdown")
    except Exception as e:
        await callback.message.edit_text(f"❌ Error generating visualization: {e}")

    await callback.answer()
