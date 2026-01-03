from aiogram import Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.config import Config
from src.formatting import build_broadcast_buttons
from src.handlers.helpers import (
    format_broadcast_progress,
    format_failure_reasons,
    get_event_message,
    send_broadcast_messages,
)
from src.handlers.states import BroadcastStates
from src.models import Broadcast, Event, Registration, utcnow

from . import router


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, config: Config, state: FSMContext) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    event = Event.get_active()
    if not event:
        await message.answer("No active event. Create one with /newevent first.")
        return

    reg_count = (
        Registration.select()
        .where(
            Registration.event == event,
            Registration.cancelled == False,  # noqa: E712
        )
        .count()
    )

    await state.set_state(BroadcastStates.message)
    await state.update_data(event_id=event.id)
    await message.answer(
        "\n\n".join(
            [
                f"📢 *Broadcast to {event.title}*",
                f"Recipients: {reg_count} registrants",
                "Type your message:",
            ]
        ),
        parse_mode="Markdown",
    )


@router.message(BroadcastStates.message)
async def process_broadcast_message(
    message: Message, config: Config, state: FSMContext
) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    data = await state.get_data()
    event = Event.get_by_id(data["event_id"])

    await state.update_data(broadcast_text=message.text)
    await state.set_state(BroadcastStates.confirm)

    all_count = (
        Registration.select()
        .where(
            Registration.event == event,
            Registration.cancelled == False,  # noqa: E712
        )
        .count()
    )
    non_responders_count = (
        Registration.select()
        .where(
            Registration.event == event,
            Registration.cancelled == False,  # noqa: E712
            Registration.confirmed == False,  # noqa: E712
        )
        .count()
    )

    buttons, prompt = build_broadcast_buttons(
        all_count,
        non_responders_count,
        event.confirmation_sent,
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        f"📢 *Preview:*\n\n{message.text}\n\n{prompt}",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "broadcast:cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Broadcast cancelled.")
    await callback.answer()


@router.callback_query(F.data.startswith("broadcast:send:"))
async def send_broadcast(
    callback: CallbackQuery, config: Config, state: FSMContext, bot: Bot
) -> None:
    # Parse callback: broadcast:send:{buttons|no_buttons}:{all|non_responders}
    parts = callback.data.split(":")
    include_buttons = parts[2] == "buttons"
    target = parts[3] if len(parts) > 3 else "all"

    data = await state.get_data()
    event = Event.get_by_id(data["event_id"])
    broadcast_text = data["broadcast_text"]
    await state.clear()

    query = Registration.select().where(
        Registration.event == event,
        Registration.cancelled == False,  # noqa: E712
    )
    if target == "non_responders":
        query = query.where(Registration.confirmed == False)  # noqa: E712

    registrations = list(query)

    keyboard = None
    if include_buttons:
        confirm_btn_text = get_event_message(event, "confirm_button", config)
        cancel_btn_text = get_event_message(event, "cancel_button", config)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=confirm_btn_text, callback_data=f"confirm:{event.id}"
                    ),
                    InlineKeyboardButton(
                        text=cancel_btn_text, callback_data=f"cancel:{event.id}"
                    ),
                ]
            ]
        )
        if not event.confirmation_sent:
            event.confirmation_sent = True
            event.confirmation_sent_at = utcnow()
            event.save()

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
        keyboard,
        progress_callback=on_progress,
    )

    Broadcast.create(
        event=event,
        message_text=broadcast_text,
        target_audience=target,
        include_buttons=include_buttons,
        sent_count=sent,
        failed_count=failed,
    )

    failure_text = format_failure_reasons(failure_reasons)
    await callback.message.edit_text(
        f"✅ *Broadcast sent!*\n\n📤 Sent: {sent}\n❌ Failed: {failed}{failure_text}",
        parse_mode="Markdown",
    )
    await callback.answer()
