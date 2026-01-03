import os

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
from src.db_export import generate_and_upload_export
from src.formatting import (
    format_endevent_result,
    format_event_created,
    format_stats_message,
)
from src.handlers.helpers import (
    format_broadcast_progress,
    format_failure_reasons,
    generate_event_csv,
    get_event_stats,
    is_valid_event_code,
    send_broadcast_messages,
    suggest_event_code,
)
from src.handlers.states import EndBroadcastStates, NewEventStates
from src.models import Broadcast, Event, Registration, utcnow

from . import router


@router.message(Command("newevent"))
async def cmd_newevent(message: Message, config: Config, state: FSMContext) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    if Event.get_active():
        await message.answer("⚠️ There's already an active event. Use /endevent first.")
        return

    await state.set_state(NewEventStates.title)
    await message.answer(
        "📝 *New Event*\n\nWhat's the event title?", parse_mode="Markdown"
    )


@router.message(NewEventStates.title)
async def process_event_title(
    message: Message, config: Config, state: FSMContext
) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    await state.update_data(title=message.text)
    await state.set_state(NewEventStates.description)
    await message.answer("📄 Description?")


@router.message(NewEventStates.description)
async def process_event_description(
    message: Message, config: Config, state: FSMContext
) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    await state.update_data(description=message.text)
    await state.set_state(NewEventStates.datetime_text)
    await message.answer("📅 When? (any format, e.g. 'January 15, 2025 at 7pm UTC')")


@router.message(NewEventStates.datetime_text)
async def process_event_datetime(
    message: Message, config: Config, state: FSMContext
) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    await state.update_data(datetime_text=message.text)
    data = await state.get_data()
    suggested = suggest_event_code(data["title"])

    await state.set_state(NewEventStates.event_code)
    await message.answer(
        "\n\n".join(
            [
                "🔗 Event code for the registration link?",
                f"Only a-z, 0-9, _ allowed. Example: {suggested}",
            ]
        ),
    )


@router.message(NewEventStates.event_code)
async def process_event_code(
    message: Message, config: Config, state: FSMContext
) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    code = message.text.lower().strip()

    if not is_valid_event_code(code):
        await message.answer(
            "❌ Invalid code. Only lowercase letters, numbers, and underscores allowed.\n"
            "Try again:"
        )
        return

    existing = Event.get_or_none(Event.code == code)
    if existing:
        await message.answer(
            f"❌ Code `{code}` is already used. Try a different one:",
            parse_mode="Markdown",
        )
        return

    await state.update_data(event_code=code)
    await state.set_state(NewEventStates.custom_question)
    await message.answer(
        "❓ Custom question for registrants?\n\n_(Type question or /skip)_",
        parse_mode="Markdown",
    )


@router.message(NewEventStates.custom_question)
async def process_custom_question(
    message: Message, config: Config, state: FSMContext, bot: Bot
) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    if message.text == "/skip":
        data = await state.get_data()
        event = Event.create(
            title=data["title"],
            description=data["description"],
            datetime_text=data["datetime_text"],
            code=data["event_code"],
        )
        await state.clear()

        bot_info = await bot.get_me()
        link = f"https://t.me/{bot_info.username}?start={data['event_code']}"
        await message.answer(
            format_event_created(event.title, link),
            parse_mode="Markdown",
        )
        return

    await state.update_data(custom_question=message.text)
    await state.set_state(NewEventStates.question_type)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Free text", callback_data="qtype:text"),
                InlineKeyboardButton(text="Options", callback_data="qtype:options"),
            ]
        ]
    )
    await message.answer("Answer type?", reply_markup=keyboard)


@router.callback_query(F.data.startswith("qtype:"))
async def process_question_type(
    callback: CallbackQuery, config: Config, state: FSMContext, bot: Bot
) -> None:
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    qtype = callback.data.split(":")[1]
    await state.update_data(question_type=qtype)

    if qtype == "text":
        data = await state.get_data()
        event = Event.create(
            title=data["title"],
            description=data["description"],
            datetime_text=data["datetime_text"],
            code=data["event_code"],
            custom_question=data["custom_question"],
            question_type="text",
        )
        await state.clear()

        bot_info = await bot.get_me()
        link = f"https://t.me/{bot_info.username}?start={data['event_code']}"
        await callback.message.edit_text(
            format_event_created(
                event.title,
                link,
                custom_question=event.custom_question,
            ),
            parse_mode="Markdown",
        )
    else:
        await state.set_state(NewEventStates.question_options)
        await callback.message.edit_text(
            "Enter options, comma-separated:\n\n_(e.g. Beginner, Intermediate, Advanced)_"
        )

    await callback.answer()


@router.message(NewEventStates.question_options)
async def process_question_options(
    message: Message, config: Config, state: FSMContext, bot: Bot
) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    data = await state.get_data()
    event = Event.create(
        title=data["title"],
        description=data["description"],
        datetime_text=data["datetime_text"],
        code=data["event_code"],
        custom_question=data["custom_question"],
        question_type="options",
        question_options=message.text,
    )
    await state.clear()

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={data['event_code']}"
    await message.answer(
        format_event_created(
            event.title,
            link,
            custom_question=event.custom_question,
            options=event.get_options_list(),
        ),
        parse_mode="Markdown",
    )


@router.message(Command("endevent"))
async def cmd_endevent(message: Message, config: Config) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    event = Event.get_active()
    if not event:
        await message.answer("No active event to end.")
        return

    stats = get_event_stats(event)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📤 Export CSV", callback_data=f"endevent:export:{event.id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📢 End & Broadcast",
                    callback_data=f"endevent:end:{event.id}:broadcast",
                ),
                InlineKeyboardButton(
                    text="🗑 End silently",
                    callback_data=f"endevent:end:{event.id}:silent",
                ),
            ],
            [
                InlineKeyboardButton(text="❌ Cancel", callback_data="endevent:cancel"),
            ],
        ]
    )

    await message.answer(
        f'📊 *End event "{event.title}"?*\n\n'
        f"Registered: {stats['registered']}\n"
        f"Confirmed: {stats['confirmed']}\n"
        f"Cancelled: {stats['cancelled']}\n"
        f"Pending: {stats['pending']}",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("endevent:export:"))
async def handle_endevent_export(
    callback: CallbackQuery, config: Config, bot: Bot
) -> None:
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    event_id = int(callback.data.split(":")[2])
    event = Event.get_or_none(
        Event.id == event_id,
        Event.is_active == True,  # noqa: E712
    )
    if not event:
        await callback.answer("Event not found or already ended")
        return

    output = generate_event_csv(event)
    file = BufferedInputFile(
        output.getvalue().encode("utf-8"),
        filename=f"{event.code}_registrations.csv",
    )
    await bot.send_document(
        callback.message.chat.id,
        file,
        caption=f"📋 Registrations for {event.title}",
    )
    await callback.answer("CSV exported!")


@router.callback_query(F.data.startswith("endevent:end:"))
async def handle_endevent_confirm(
    callback: CallbackQuery, config: Config, state: FSMContext
) -> None:
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    parts = callback.data.split(":")
    event_id = int(parts[2])
    mode = parts[3]  # 'broadcast' or 'silent'

    event = Event.get_or_none(
        Event.id == event_id,
        Event.is_active == True,  # noqa: E712
    )
    if not event:
        await callback.answer("Event not found or already ended")
        return

    event.is_active = False
    event.archived_at = utcnow()
    event.save()

    stats = get_event_stats(event)

    if mode == "broadcast":
        reg_count = (
            Registration.select()
            .where(
                Registration.event == event,
                Registration.cancelled == False,  # noqa: E712
            )
            .count()
        )

        if reg_count == 0:
            result_text = format_endevent_result(event.title, stats, False, 0, 0)
            await callback.message.edit_text(result_text, parse_mode="Markdown")
            await callback.answer()
            return

        template = config.registration.event_ended_notification.format(
            event_title=event.title
        )

        await state.set_state(EndBroadcastStates.message)
        await state.update_data(event_id=event.id)

        intro = config.broadcast.end_event_intro.format(
            event_title=event.title,
            count=reg_count,
            template=template,
        )
        await callback.message.edit_text(intro, parse_mode="Markdown")
    else:
        result_text = format_endevent_result(event.title, stats, False, 0, 0)
        await callback.message.edit_text(result_text, parse_mode="Markdown")

    await callback.answer()


@router.callback_query(F.data == "endevent:cancel")
async def handle_endevent_cancel(callback: CallbackQuery, config: Config) -> None:
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    await callback.message.edit_text("❌ End event cancelled.")
    await callback.answer()


# --- End Broadcast Handlers ---


@router.message(EndBroadcastStates.message)
async def process_end_broadcast_message(
    message: Message, config: Config, state: FSMContext
) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    data = await state.get_data()
    event = Event.get_by_id(data["event_id"])

    await state.update_data(broadcast_text=message.text)
    await state.set_state(EndBroadcastStates.confirm)

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
                    callback_data=f"endbc:send:{event.id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel (already archived)",
                    callback_data=f"endbc:cancel:{event.id}",
                ),
            ],
        ]
    )

    await message.answer(
        f"📢 *Preview:*\n\n{message.text}\n\n_Send to {reg_count} registrants of {event.title}?_",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("endbc:send:"))
async def handle_end_broadcast_send(
    callback: CallbackQuery, config: Config, state: FSMContext, bot: Bot
) -> None:
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    event_id = int(callback.data.split(":")[2])
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

    stats = get_event_stats(event)
    result_text = format_endevent_result(
        event.title, stats, True, sent, failed, format_failure_reasons(failure_reasons)
    )
    await callback.message.edit_text(result_text, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data.startswith("endbc:cancel:"))
async def handle_end_broadcast_cancel(
    callback: CallbackQuery, config: Config, state: FSMContext
) -> None:
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    event_id = int(callback.data.split(":")[2])
    event = Event.get_or_none(Event.id == event_id)

    await state.clear()

    if event:
        stats = get_event_stats(event)
        result_text = format_endevent_result(event.title, stats, False, 0, 0)
        await callback.message.edit_text(result_text, parse_mode="Markdown")
    else:
        await callback.message.edit_text("❌ Broadcast cancelled. Event archived.")

    await callback.answer()


@router.message(Command("version"))
async def cmd_version(message: Message, config: Config) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    version = os.environ.get("BOT_VERSION", "dev")
    await message.answer(f"🤖 Bot version: `{version}`", parse_mode="Markdown")


@router.message(Command("dbexport"))
async def cmd_dbexport(message: Message, config: Config) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    await message.answer(config.dbexport.generating)

    try:
        result, stats, is_url = generate_and_upload_export()

        if is_url:
            await message.answer(
                config.dbexport.success_url.format(
                    tables=stats["tables"],
                    rows=stats["rows"],
                    url=result,
                )
            )
        else:
            file = BufferedInputFile(result, filename="workshop_bot_export.db")
            await message.answer_document(
                file,
                caption=config.dbexport.success.format(
                    tables=stats["tables"],
                    rows=stats["rows"],
                ),
            )
    except Exception as e:
        await message.answer(config.dbexport.error.format(error=str(e)))


@router.message(Command("stats"))
async def cmd_stats(message: Message, config: Config) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    event = Event.get_active()
    if not event:
        await message.answer("No active event.")
        return

    stats = get_event_stats(event)

    options = None
    answer_counts = None
    if event.question_type == "options":
        options = event.get_options_list()
        answer_counts = {}
        for opt in options:
            answer_counts[opt] = (
                Registration.select()
                .where(
                    Registration.event == event,
                    Registration.cancelled == False,  # noqa: E712
                    Registration.answer == opt,
                )
                .count()
            )

    text = format_stats_message(event.title, stats, options, answer_counts)
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("export"))
async def cmd_export(message: Message, config: Config) -> None:
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    event = Event.get_active()
    if not event:
        await message.answer("No active event.")
        return

    output = generate_event_csv(event)
    file = BufferedInputFile(
        output.getvalue().encode("utf-8"), filename=f"{event.code}_registrations.csv"
    )
    await message.answer_document(file, caption=f"📋 Registrations for {event.title}")
