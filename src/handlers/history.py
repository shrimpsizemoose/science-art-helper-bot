from aiogram import Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.config import Config
from src.export import generate_broadcasts_json
from src.formatting import format_history_list
from src.handlers.helpers import (
    format_broadcast_progress,
    format_failure_reasons,
    generate_event_csv,
    get_event_stats,
    send_broadcast_messages,
)
from src.handlers.states import HistoryBroadcastStates
from src.models import Broadcast, Event, Registration

from . import router


@router.message(Command("history"))
async def cmd_history(message: Message, config: Config) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    archived_events = (
        Event.select()
        .where(Event.is_active == False)  # noqa: E712
        .order_by(Event.archived_at.desc())
        .limit(10)
    )

    events_list = list(archived_events)
    if not events_list:
        await message.answer("No archived events yet.")
        return

    events_data = []
    for event in events_list:
        stats = get_event_stats(event)
        archived_date = (
            event.archived_at.strftime("%b %d, %Y") if event.archived_at else "Unknown"
        )
        events_data.append((event.id, event.title, archived_date, stats))

    text, export_buttons, broadcast_buttons = format_history_list(events_data)

    export_rows = [export_buttons[i : i + 5] for i in range(0, len(export_buttons), 5)]
    broadcast_rows = [
        broadcast_buttons[i : i + 5] for i in range(0, len(broadcast_buttons), 5)
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=export_rows + broadcast_rows)

    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@router.callback_query(F.data.startswith("history:export:"))
async def handle_history_export(
    callback: CallbackQuery, config: Config, bot: Bot
) -> None:
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    event_id = int(callback.data.split(":")[2])
    event = Event.get_or_none(Event.id == event_id)
    if not event:
        await callback.answer("Event not found")
        return

    output = generate_event_csv(event)
    file = BufferedInputFile(
        output.getvalue().encode("utf-8"), filename=f"{event.code}_registrations.csv"
    )
    await bot.send_document(
        callback.message.chat.id, file, caption=f"📋 Registrations for {event.title}"
    )
    await callback.answer("CSV exported!")


@router.callback_query(F.data.startswith("history:broadcast:send:"))
async def handle_history_broadcast_send(
    callback: CallbackQuery, config: Config, state: FSMContext, bot: Bot
) -> None:
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    event_id = int(callback.data.split(":")[3])
    data = await state.get_data()
    broadcast_text = data.get("broadcast_text")

    if not broadcast_text:
        await callback.answer("No message to send")
        return

    event = Event.get_or_none(Event.id == event_id)
    if not event:
        await callback.answer("Event not found")
        await state.clear()
        return

    registrations = list(
        Registration.select().where(
            Registration.event == event,
            Registration.cancelled == False,  # noqa: E712
        )
    )

    total = len(registrations)
    await callback.message.edit_text(
        format_broadcast_progress(0, 0, total, 0),
        parse_mode="Markdown",
    )

    async def on_progress(sent: int, failed: int, total: int, processed: int) -> None:
        await callback.message.edit_text(
            format_broadcast_progress(sent, failed, total, processed),
            parse_mode="Markdown",
        )

    sent, failed, failure_reasons = await send_broadcast_messages(
        bot,
        registrations,
        broadcast_text,
        progress_callback=on_progress,
    )

    Broadcast.create(
        event=event,
        message_text=broadcast_text,
        target_audience="all",
        include_buttons=False,
        sent_count=sent,
        failed_count=failed,
    )

    await state.clear()
    failure_text = format_failure_reasons(failure_reasons)
    await callback.message.edit_text(
        f"✅ *Broadcast sent to {event.title}!*\n\n📤 Sent: {sent}\n❌ Failed: {failed}{failure_text}",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "history:broadcast:cancel")
async def handle_history_broadcast_cancel(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Broadcast cancelled.")
    await callback.answer()


@router.callback_query(F.data.startswith("history:broadcast:"))
async def handle_history_broadcast_start(
    callback: CallbackQuery, config: Config, state: FSMContext
) -> None:
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    event_id = int(callback.data.split(":")[2])
    event = Event.get_or_none(Event.id == event_id)
    if not event:
        await callback.answer("Event not found")
        return

    reg_count = (
        Registration.select()
        .where(
            Registration.event == event,
            Registration.cancelled == False,  # noqa: E712
        )
        .count()
    )

    if reg_count == 0:
        await callback.answer("No registrants to message", show_alert=True)
        return

    await state.set_state(HistoryBroadcastStates.message)
    await state.update_data(event_id=event.id)

    intro = config.broadcast.history_intro.format(
        event_title=event.title,
        count=reg_count,
    )
    await callback.message.edit_text(intro, parse_mode="Markdown")
    await callback.answer()


@router.message(HistoryBroadcastStates.message)
async def process_history_broadcast_message(
    message: Message, config: Config, state: FSMContext
) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    data = await state.get_data()
    event = Event.get_by_id(data["event_id"])

    await state.update_data(broadcast_text=message.text)
    await state.set_state(HistoryBroadcastStates.confirm)

    reg_count = (
        Registration.select()
        .where(
            Registration.event == event,
            Registration.cancelled == False,  # noqa: E712
        )
        .count()
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"📤 Send to {reg_count} registrants",
                    callback_data=f"history:broadcast:send:{event.id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data="history:broadcast:cancel",
                ),
            ],
        ]
    )

    await message.answer(
        f"📢 *Preview:*\n\n{message.text}\n\n_Send to {reg_count} past registrants of {event.title}?_",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


# --- Broadcasts History Handlers ---


@router.message(Command("broadcasts"))
async def cmd_broadcasts(message: Message, config: Config) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    events_with_broadcasts = (
        Event.select().join(Broadcast).group_by(Event).order_by(Event.created_at.desc())
    )

    events_list = list(events_with_broadcasts)
    if not events_list:
        await message.answer(config.broadcast.no_history)
        return

    text = "📢 *Broadcast History*\n\n"
    buttons = []

    for i, event in enumerate(events_list, 1):
        broadcast_count = Broadcast.select().where(Broadcast.event == event).count()
        status = "Active" if event.is_active else "Archived"
        text += f"{i}. *{event.title}* ({status})\n   {broadcast_count} broadcasts\n\n"
        buttons.append(
            InlineKeyboardButton(
                text=f"{i}",
                callback_data=f"broadcasts:event:{event.id}",
            )
        )

    button_rows = [buttons[i : i + 5] for i in range(0, len(buttons), 5)]
    keyboard = InlineKeyboardMarkup(inline_keyboard=button_rows)

    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@router.callback_query(F.data.startswith("broadcasts:event:"))
async def handle_broadcasts_event(
    callback: CallbackQuery, config: Config, bot: Bot
) -> None:
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    event_id = int(callback.data.split(":")[2])
    event = Event.get_or_none(Event.id == event_id)
    if not event:
        await callback.answer("Event not found")
        return

    broadcasts = (
        Broadcast.select()
        .where(Broadcast.event == event)
        .order_by(Broadcast.sent_at.desc())
    )

    broadcasts_list = list(broadcasts)
    if not broadcasts_list:
        await callback.answer("No broadcasts for this event")
        return

    header = config.broadcast.history_header.format(event_title=event.title)
    text = header

    buttons = []
    for i, bc in enumerate(broadcasts_list, 1):
        sent_at = bc.sent_at
        if hasattr(sent_at, "strftime"):
            sent_str = sent_at.strftime("%b %d, %H:%M")
        else:
            sent_str = str(sent_at)[:16]

        preview = (
            bc.message_text[:50] + "..."
            if len(bc.message_text) > 50
            else bc.message_text
        )
        preview = preview.replace("\n", " ")

        audience = "All" if bc.target_audience == "all" else "Non-responders"
        btns = "w/ buttons" if bc.include_buttons else ""

        text += f"{i}. {sent_str} | {audience} {btns}\n"
        text += f"   📤 {bc.sent_count} ❌ {bc.failed_count}\n"
        text += f"   _{preview}_\n\n"

        buttons.append(
            InlineKeyboardButton(
                text=f"{i}",
                callback_data=f"broadcasts:detail:{bc.id}",
            )
        )

    export_btn = InlineKeyboardButton(
        text="📥 Export JSON",
        callback_data=f"broadcasts:export:{event.id}",
    )
    back_btn = InlineKeyboardButton(
        text="« Back",
        callback_data="broadcasts:back",
    )

    button_rows = [buttons[i : i + 5] for i in range(0, len(buttons), 5)]
    button_rows.append([export_btn, back_btn])
    keyboard = InlineKeyboardMarkup(inline_keyboard=button_rows)

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("broadcasts:detail:"))
async def handle_broadcasts_detail(callback: CallbackQuery, config: Config) -> None:
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    broadcast_id = int(callback.data.split(":")[2])
    bc = Broadcast.get_or_none(Broadcast.id == broadcast_id)
    if not bc:
        await callback.answer("Broadcast not found")
        return

    event = bc.event

    sent_at = bc.sent_at
    if hasattr(sent_at, "strftime"):
        sent_str = sent_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        sent_str = str(sent_at)

    audience = (
        "All registrants" if bc.target_audience == "all" else "Non-responders only"
    )
    btns = "Yes" if bc.include_buttons else "No"

    text = "📢 *Broadcast Details*\n\n"
    text += f"*Event:* {event.title}\n"
    text += f"*Sent:* {sent_str}\n"
    text += f"*Audience:* {audience}\n"
    text += f"*With buttons:* {btns}\n"
    text += f"*Delivered:* {bc.sent_count}\n"
    text += f"*Failed:* {bc.failed_count}\n\n"
    text += f"*Message:*\n{bc.message_text}"

    back_btn = InlineKeyboardButton(
        text="« Back to event",
        callback_data=f"broadcasts:event:{event.id}",
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[back_btn]])

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("broadcasts:export:"))
async def handle_broadcasts_export(
    callback: CallbackQuery, config: Config, bot: Bot
) -> None:
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    event_id = int(callback.data.split(":")[2])
    event = Event.get_or_none(Event.id == event_id)
    if not event:
        await callback.answer("Event not found")
        return

    json_data = generate_broadcasts_json(event)

    file = BufferedInputFile(
        json_data.encode("utf-8"),
        filename=f"{event.code}_broadcasts.json",
    )
    await bot.send_document(
        callback.message.chat.id,
        file,
        caption=f"📊 Broadcast history for {event.title}",
    )
    await callback.answer("JSON exported!")


@router.callback_query(F.data == "broadcasts:back")
async def handle_broadcasts_back(callback: CallbackQuery, config: Config) -> None:
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    events_with_broadcasts = (
        Event.select().join(Broadcast).group_by(Event).order_by(Event.created_at.desc())
    )

    events_list = list(events_with_broadcasts)
    if not events_list:
        await callback.message.edit_text(config.broadcast.no_history)
        await callback.answer()
        return

    text = "📢 *Broadcast History*\n\n"
    buttons = []

    for i, event in enumerate(events_list, 1):
        broadcast_count = Broadcast.select().where(Broadcast.event == event).count()
        status = "Active" if event.is_active else "Archived"
        text += f"{i}. *{event.title}* ({status})\n   {broadcast_count} broadcasts\n\n"
        buttons.append(
            InlineKeyboardButton(
                text=f"{i}",
                callback_data=f"broadcasts:event:{event.id}",
            )
        )

    button_rows = [buttons[i : i + 5] for i in range(0, len(buttons), 5)]
    keyboard = InlineKeyboardMarkup(inline_keyboard=button_rows)

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()
