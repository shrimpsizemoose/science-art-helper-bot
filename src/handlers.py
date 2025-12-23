import csv
import io
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.config import Config
from src.models import Event, Registration, User, utcnow

router = Router()


# --- FSM States ---


class NewEventStates(StatesGroup):
    title = State()
    description = State()
    datetime_text = State()
    event_code = State()
    custom_question = State()
    question_type = State()
    question_options = State()


class BroadcastStates(StatesGroup):
    message = State()
    confirm = State()


class RegistrationStates(StatesGroup):
    answer = State()


# --- Helpers ---


def is_valid_event_code(code: str) -> bool:
    """Check if code is valid for Telegram deep links (a-z, 0-9, _)."""  # noqa: DOC201
    return bool(re.match(r"^[a-z0-9_]+$", code)) and len(code) <= 64


def suggest_event_code(title: str) -> str:
    """Generate a suggested event code from title (ASCII only)."""  # noqa: DOC201
    code = title.lower().strip()
    code = re.sub(r"[^a-z0-9\s-]", "", code)
    code = re.sub(r"[-\s]+", "_", code)
    code = code.strip("_")
    if not code:
        # Fallback for non-ASCII titles
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
    return getattr(config.default_event_messages, key)


def generate_event_csv(event: Event) -> io.StringIO:
    """Generate CSV data for event registrations."""  # noqa: DOC201
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


def get_event_stats(event: Event) -> dict:
    """Get registration statistics for an event."""  # noqa: DOC201
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


# --- User Handlers ---


@router.message(CommandStart(deep_link=True))
async def cmd_start_with_code(
    message: Message, command: CommandObject, config: Config
) -> None:
    """Handle /start with event code (deep link registration)."""
    event_code = command.args
    event = (
        Event.select().where(Event.code == event_code, Event.is_active == True).first()  # noqa: E712
    )

    if not event:
        await message.answer(config.system_messages.event_not_available)
        return

    user = get_or_create_user(message.from_user)

    # Check if already registered
    existing = (
        Registration.select()
        .where(
            Registration.user == user,
            Registration.event == event,
            Registration.cancelled == False,  # noqa: E712
        )
        .first()
    )

    if existing:
        msg = get_event_message(event, "already_registered", config)
        await message.answer(
            msg.format(event_title=event.title, user_name=user.display_name)
        )
        return

    # Show event info with register button (same as plain /start)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=config.system_messages.register_button_text,
                    callback_data=f"register:{event.id}",
                )
            ]
        ]
    )
    await message.answer(
        f"📋 *{event.title}*\n\n{event.description}\n\n📅 {event.datetime_text}",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@router.message(CommandStart())
async def cmd_start(message: Message, config: Config) -> None:
    """Handle plain /start - show current event or no-event message."""
    event = Event.get_active()

    if not event:
        await message.answer(config.system_messages.no_active_event)
        return

    user = get_or_create_user(message.from_user)

    # Check if already registered
    existing = (
        Registration.select()
        .where(
            Registration.user == user,
            Registration.event == event,
            Registration.cancelled == False,  # noqa: E712
        )
        .first()
    )

    if existing:
        msg = get_event_message(event, "already_registered", config)
        await message.answer(
            msg.format(event_title=event.title, user_name=user.display_name)
        )
        return

    # Show event info with register button
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=config.system_messages.register_button_text,
                    callback_data=f"register:{event.id}",
                )
            ]
        ]
    )
    await message.answer(
        f"📋 *{event.title}*\n\n{event.description}\n\n📅 {event.datetime_text}",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("answer:"))
async def handle_option_answer(
    callback: CallbackQuery, config: Config, state: FSMContext
) -> None:
    """Handle option button click for custom question."""
    answer = callback.data.split(":", 1)[1]
    data = await state.get_data()

    event = Event.get_by_id(data["event_id"])
    user = User.get_by_id(data["user_id"])

    Registration.create(user=user, event=event, answer=answer)
    await state.clear()

    msg = get_event_message(event, "registration_success", config)
    await callback.message.edit_text(
        f"✅ {msg.format(event_title=event.title, user_name=user.display_name)}"
    )
    await callback.answer()


@router.message(RegistrationStates.answer)
async def handle_text_answer(
    message: Message, config: Config, state: FSMContext
) -> None:
    """Handle text answer for custom question."""
    data = await state.get_data()

    event = Event.get_by_id(data["event_id"])
    user = User.get_by_id(data["user_id"])

    answer = None if message.text == "/skip" else message.text
    Registration.create(user=user, event=event, answer=answer)
    await state.clear()

    msg = get_event_message(event, "registration_success", config)
    await message.answer(
        f"✅ {msg.format(event_title=event.title, user_name=user.display_name)}"
    )


@router.callback_query(F.data == "answer_skip")
async def handle_skip_answer(
    callback: CallbackQuery, config: Config, state: FSMContext
) -> None:
    """Handle skip button click for custom question."""
    data = await state.get_data()

    event = Event.get_by_id(data["event_id"])
    user = User.get_by_id(data["user_id"])

    Registration.create(user=user, event=event, answer=None)
    await state.clear()

    msg = get_event_message(event, "registration_success", config)
    await callback.message.edit_text(
        f"✅ {msg.format(event_title=event.title, user_name=user.display_name)}"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm:"))
async def handle_confirm_attendance(callback: CallbackQuery, config: Config) -> None:
    """Handle confirm button click from broadcast message."""
    event_id = int(callback.data.split(":")[1])

    event = Event.get_or_none(Event.id == event_id)
    if not event:
        await callback.answer("Event not found")
        return

    if not event.is_active:
        await callback.answer(
            config.system_messages.event_already_ended, show_alert=True
        )
        return

    user = User.get_or_none(User.telegram_id == callback.from_user.id)
    if not user:
        await callback.answer("User not found")
        return

    registration = Registration.get_or_none(
        Registration.user == user,
        Registration.event == event,
        Registration.cancelled == False,  # noqa: E712
    )

    if not registration:
        await callback.answer("Registration not found")
        return

    if registration.confirmed:
        await callback.answer("Already confirmed!")
        return

    registration.confirmed = True
    registration.confirmed_at = utcnow()
    registration.save()

    msg = get_event_message(event, "confirm_confirmation", config)
    await callback.message.edit_text(
        msg.format(event_title=event.title, user_name=user.display_name)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel:"))
async def handle_cancel_registration(callback: CallbackQuery, config: Config) -> None:
    """Handle cancel button click from broadcast message."""
    event_id = int(callback.data.split(":")[1])

    event = Event.get_or_none(Event.id == event_id)
    if not event:
        await callback.answer("Event not found")
        return

    if not event.is_active:
        await callback.answer(
            config.system_messages.event_already_ended, show_alert=True
        )
        return

    user = User.get_or_none(User.telegram_id == callback.from_user.id)
    if not user:
        await callback.answer("User not found")
        return

    registration = Registration.get_or_none(
        Registration.user == user,
        Registration.event == event,
        Registration.cancelled == False,  # noqa: E712
    )

    if not registration:
        await callback.answer("Registration not found")
        return

    registration.cancelled = True
    registration.cancelled_at = utcnow()
    registration.save()

    msg = get_event_message(event, "cancel_confirmation", config)
    await callback.message.edit_text(
        msg.format(event_title=event.title, user_name=user.display_name)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("register:"))
async def handle_register_button(
    callback: CallbackQuery, config: Config, state: FSMContext
) -> None:
    """Handle register button click from /start message."""
    event_id = int(callback.data.split(":")[1])

    event = Event.get_or_none(Event.id == event_id, Event.is_active == True)  # noqa: E712
    if not event:
        await callback.answer(config.system_messages.event_not_available)
        return

    user = get_or_create_user(callback.from_user)

    # Check if already registered
    existing = (
        Registration.select()
        .where(
            Registration.user == user,
            Registration.event == event,
            Registration.cancelled == False,  # noqa: E712
        )
        .first()
    )

    if existing:
        msg = get_event_message(event, "already_registered", config)
        await callback.answer(
            msg.format(event_title=event.title, user_name=user.display_name),
            show_alert=True,
        )
        return

    # If event has custom question, ask it
    if event.custom_question:
        await state.update_data(event_id=event.id, user_id=user.id)

        if event.question_type == "options":
            options = event.get_options_list()
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=opt, callback_data=f"answer:{opt}")]
                    for opt in options
                ]
                + [
                    [
                        InlineKeyboardButton(
                            text=config.system_messages.skip_question_button_text,
                            callback_data="answer_skip",
                        )
                    ]
                ]
            )
            await callback.message.edit_text(
                f"📋 *{event.title}*\n\n"
                f"{config.system_messages.question_intro}\n\n"
                f"{event.custom_question}",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        else:
            await state.set_state(RegistrationStates.answer)
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=config.system_messages.skip_question_button_text,
                            callback_data="answer_skip",
                        )
                    ]
                ]
            )
            await callback.message.edit_text(
                f"📋 *{event.title}*\n\n"
                f"{config.system_messages.question_intro}\n\n"
                f"{event.custom_question}",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        await callback.answer()
        return

    # No custom question - register directly
    Registration.create(user=user, event=event)
    msg = get_event_message(event, "registration_success", config)
    await callback.message.edit_text(
        f"✅ {msg.format(event_title=event.title, user_name=user.display_name)}"
    )
    await callback.answer()


# --- Admin Handlers ---


def admin_check(config: Config):  # noqa: ANN201
    """Create filter for admin commands."""  # noqa: DOC201

    async def check(message: Message) -> bool:  # noqa: RUF029
        return config.is_admin_context(message.chat.id, message.from_user.id)

    return check


@router.message(Command("newevent"))
async def cmd_newevent(message: Message, config: Config, state: FSMContext) -> None:
    """Start new event creation wizard."""
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    # Check if there's already an active event
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
    """Process event title."""
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    await state.update_data(title=message.text)
    await state.set_state(NewEventStates.description)
    await message.answer("📄 Description?")


@router.message(NewEventStates.description)
async def process_event_description(
    message: Message, config: Config, state: FSMContext
) -> None:
    """Process event description."""
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    await state.update_data(description=message.text)
    await state.set_state(NewEventStates.datetime_text)
    await message.answer("📅 When? (any format, e.g. 'January 15, 2025 at 7pm UTC')")


@router.message(NewEventStates.datetime_text)
async def process_event_datetime(
    message: Message, config: Config, state: FSMContext
) -> None:
    """Process event datetime."""
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    await state.update_data(datetime_text=message.text)
    data = await state.get_data()
    suggested = suggest_event_code(data["title"])

    await state.set_state(NewEventStates.event_code)
    await message.answer(
        f"🔗 Event code for the registration link?\n\n"
        f"Only a-z, 0-9, _ allowed. Example: {suggested}",
    )


@router.message(NewEventStates.event_code)
async def process_event_code(
    message: Message, config: Config, state: FSMContext
) -> None:
    """Process event code."""
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    code = message.text.lower().strip()

    if not is_valid_event_code(code):
        await message.answer(
            "❌ Invalid code. Only lowercase letters, numbers, and underscores allowed.\n"
            "Try again:"
        )
        return

    # Check if code already exists
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
    """Process custom question."""
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    if message.text == "/skip":
        # No custom question - create event
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
            f"✅ *Event created!*\n\n📋 {event.title}\n🔗 Registration link:\n`{link}`",
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
    """Process question type selection."""
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    qtype = callback.data.split(":")[1]
    await state.update_data(question_type=qtype)

    if qtype == "text":
        # Create event with text question
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
            f"✅ *Event created!*\n\n"
            f"📋 {event.title}\n"
            f"❓ Question: {event.custom_question}\n"
            f"🔗 Registration link:\n`{link}`",
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
    """Process question options."""
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
    options = event.get_options_list()
    await message.answer(
        f"✅ *Event created!*\n\n"
        f"📋 {event.title}\n"
        f"❓ Question: {event.custom_question}\n"
        f"📝 Options: {', '.join(options)}\n"
        f"🔗 Registration link:\n`{link}`",
        parse_mode="Markdown",
    )


@router.message(Command("endevent"))
async def cmd_endevent(message: Message, config: Config) -> None:
    """Show confirmation dialog before archiving event."""
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
                    text="✅ End & notify",
                    callback_data=f"endevent:end:{event.id}:notify",
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
    """Export CSV before ending event."""
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    event_id = int(callback.data.split(":")[2])
    event = Event.get_or_none(Event.id == event_id, Event.is_active == True)  # noqa: E712
    if not event:
        await callback.answer("Event not found or already ended")
        return

    output = generate_event_csv(event)
    file = BufferedInputFile(
        output.getvalue().encode("utf-8"), filename=f"{event.code}_registrations.csv"
    )
    await bot.send_document(
        callback.message.chat.id, file, caption=f"📋 Registrations for {event.title}"
    )
    await callback.answer("CSV exported!")


@router.callback_query(F.data.startswith("endevent:end:"))
async def handle_endevent_confirm(
    callback: CallbackQuery, config: Config, bot: Bot
) -> None:
    """Archive event and optionally notify participants."""
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    parts = callback.data.split(":")
    event_id = int(parts[2])
    notify = parts[3] == "notify"

    event = Event.get_or_none(Event.id == event_id, Event.is_active == True)  # noqa: E712
    if not event:
        await callback.answer("Event not found or already ended")
        return

    # Archive the event
    event.is_active = False
    event.archived_at = utcnow()
    event.save()

    stats = get_event_stats(event)

    # Notify participants if requested
    sent = 0
    failed = 0
    if notify:
        registrations = Registration.select().where(
            Registration.event == event,
            Registration.cancelled == False,  # noqa: E712
        )
        notification_msg = config.system_messages.event_ended_notification.format(
            event_title=event.title
        )
        for reg in registrations:
            try:
                await bot.send_message(reg.user.telegram_id, notification_msg)
                sent += 1
            except Exception:
                failed += 1

    result_text = (
        f'✅ *Event "{event.title}" archived.*\n\n'
        f"📊 Final stats:\n"
        f"Registered: {stats['registered']}\n"
        f"Confirmed: {stats['confirmed']}\n"
        f"Cancelled: {stats['cancelled']}"
    )
    if notify:
        result_text += f"\n\n📤 Notifications sent: {sent}"
        if failed:
            result_text += f" (failed: {failed})"

    result_text += "\n\nUse /history to view past events."

    await callback.message.edit_text(result_text, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "endevent:cancel")
async def handle_endevent_cancel(callback: CallbackQuery, config: Config) -> None:
    """Cancel end event operation."""
    if not config.is_admin_context(callback.message.chat.id, callback.from_user.id):
        return

    await callback.message.edit_text("❌ End event cancelled.")
    await callback.answer()


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, config: Config, state: FSMContext) -> None:
    """Start broadcast to event registrants."""
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
        f"📢 *Broadcast to {event.title}*\n\n"
        f"Recipients: {reg_count} registrants\n\n"
        f"Type your message:",
        parse_mode="Markdown",
    )


@router.message(BroadcastStates.message)
async def process_broadcast_message(
    message: Message, config: Config, state: FSMContext
) -> None:
    """Process broadcast message and ask for confirmation."""
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    data = await state.get_data()
    event = Event.get_by_id(data["event_id"])

    await state.update_data(broadcast_text=message.text)
    await state.set_state(BroadcastStates.confirm)

    # Count recipients
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

    buttons = []
    if event.confirmation_sent:
        # Confirmation already sent - offer smart targeting
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"📤 Send to all ({all_count})",
                    callback_data="broadcast:send:no_buttons:all",
                ),
            ]
        )
        if non_responders_count > 0 and non_responders_count < all_count:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"🎯 Send to non-responders ({non_responders_count}) + buttons",
                        callback_data="broadcast:send:buttons:non_responders",
                    ),
                ]
            )
        prompt = "_Confirmation was already sent. Choose recipients:_"
    else:
        # First broadcast - offer button options
        buttons.append(
            [
                InlineKeyboardButton(
                    text="✅ Include participation confirmation buttons",
                    callback_data="broadcast:send:buttons:all",
                ),
            ]
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    text="📤 Send without buttons",
                    callback_data="broadcast:send:no_buttons:all",
                ),
            ]
        )
        prompt = "_Include participation confirmation buttons?_"

    buttons.append(
        [
            InlineKeyboardButton(text="❌ Cancel", callback_data="broadcast:cancel"),
        ]
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        f"📢 *Preview:*\n\n{message.text}\n\n{prompt}",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "broadcast:cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel broadcast."""
    await state.clear()
    await callback.message.edit_text("❌ Broadcast cancelled.")
    await callback.answer()


@router.callback_query(F.data.startswith("broadcast:send:"))
async def send_broadcast(
    callback: CallbackQuery, config: Config, state: FSMContext, bot: Bot
) -> None:
    """Send broadcast to registrants."""
    # Parse callback: broadcast:send:{buttons|no_buttons}:{all|non_responders}
    parts = callback.data.split(":")
    include_buttons = parts[2] == "buttons"
    target = parts[3] if len(parts) > 3 else "all"

    data = await state.get_data()
    event = Event.get_by_id(data["event_id"])
    broadcast_text = data["broadcast_text"]
    await state.clear()

    # Build query based on targeting
    query = Registration.select().where(
        Registration.event == event,
        Registration.cancelled == False,  # noqa: E712
    )
    if target == "non_responders":
        query = query.where(Registration.confirmed == False)  # noqa: E712

    registrations = query

    keyboard = None
    if include_buttons:
        confirm_btn_text = get_event_message(event, "confirm_button_text", config)
        cancel_btn_text = get_event_message(event, "cancel_button_text", config)
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
        # Mark that confirmation was sent for this event
        if not event.confirmation_sent:
            event.confirmation_sent = True
            event.confirmation_sent_at = utcnow()
            event.save()

    sent = 0
    failed = 0

    for reg in registrations:
        try:
            await bot.send_message(
                reg.user.telegram_id,
                broadcast_text,
                reply_markup=keyboard,
            )
            sent += 1
        except Exception:
            failed += 1

    await callback.message.edit_text(
        f"✅ *Broadcast sent!*\n\n📤 Sent: {sent}\n❌ Failed: {failed}",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(Command("stats"))
async def cmd_stats(message: Message, config: Config) -> None:
    """Show registration stats for current event."""
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    event = Event.get_active()
    if not event:
        await message.answer("No active event.")
        return

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

    text = (
        f"📊 *Stats: {event.title}*\n\n"
        f"🎉 Confirmed: {confirmed}\n"
        f"📋 Registered: {active}\n"
        f"❌ Cancelled: {cancelled}"
    )

    # If there's a custom question with options, show answer breakdown
    if event.question_type == "options":
        text += "\n\n*Answers:*"
        for opt in event.get_options_list():
            count = (
                Registration.select()
                .where(
                    Registration.event == event,
                    Registration.cancelled == False,  # noqa: E712
                    Registration.answer == opt,
                )
                .count()
            )
            text += f"\n• {opt}: {count}"

    await message.answer(text, parse_mode="Markdown")


@router.message(Command("export"))
async def cmd_export(message: Message, config: Config) -> None:
    """Export registrations as CSV."""
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


@router.message(Command("history"))
async def cmd_history(message: Message, config: Config) -> None:
    """Show archived events."""
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

    text = "📜 *Past Events:*\n"
    buttons = []

    for i, event in enumerate(events_list, 1):
        stats = get_event_stats(event)
        archived_date = (
            event.archived_at.strftime("%b %d, %Y") if event.archived_at else "Unknown"
        )
        text += (
            f"\n*{i}. {event.title}* ({archived_date})\n"
            f"   Registered: {stats['registered']} | Confirmed: {stats['confirmed']}\n"
        )
        buttons.append(
            InlineKeyboardButton(
                text=f"📤 #{i}", callback_data=f"history:export:{event.id}"
            )
        )

    # Arrange buttons in rows of 5
    button_rows = [buttons[i : i + 5] for i in range(0, len(buttons), 5)]
    keyboard = InlineKeyboardMarkup(inline_keyboard=button_rows)

    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)


@router.callback_query(F.data.startswith("history:export:"))
async def handle_history_export(
    callback: CallbackQuery, config: Config, bot: Bot
) -> None:
    """Export CSV for archived event."""
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


# --- Fallback Handler ---


@router.message()
async def handle_unknown_message(message: Message, config: Config) -> None:
    """Handle any unrecognized message."""
    await message.answer(config.system_messages.unknown_message)
