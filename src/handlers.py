import csv
import io
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
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
    custom_question = State()
    question_type = State()
    question_options = State()


class BroadcastStates(StatesGroup):
    message = State()
    confirm = State()


class RegistrationStates(StatesGroup):
    answer = State()


# --- Helpers ---


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "_", text)
    return text[:50]


def get_or_create_user(tg_user) -> User:
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


# --- User Handlers ---


@router.message(CommandStart(deep_link=True))
async def cmd_start_with_code(
    message: Message, command: CommandObject, config: Config, state: FSMContext
):
    """Handle /start with event code (deep link registration)."""
    event_code = command.args
    event = (
        Event.select().where(Event.code == event_code, Event.is_active == True).first()
    )  # noqa: E712

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
            )
            await message.answer(
                f"📋 *{event.title}*\n\n{event.custom_question}",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        else:
            await state.set_state(RegistrationStates.answer)
            await message.answer(
                f"📋 *{event.title}*\n\n{event.custom_question}\n\n_(напишите ответ или /skip)_",
                parse_mode="Markdown",
            )
        return

    # No custom question - register directly
    Registration.create(user=user, event=event)
    msg = get_event_message(event, "registration_success", config)
    await message.answer(
        msg.format(event_title=event.title, user_name=user.display_name)
    )


@router.message(CommandStart())
async def cmd_start(message: Message, config: Config) -> None:
    """Handle plain /start - show current event or no-event message."""
    event = Event.get_active()

    if not event:
        await message.answer(config.system_messages.no_active_event)
        return

    # Show event info
    await message.answer(
        f"📋 *{event.title}*\n\n"
        f"{event.description}\n\n"
        f"📅 {event.datetime_text}\n\n"
        f"Use the registration link to sign up!",
        parse_mode="Markdown",
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


@router.callback_query(F.data.startswith("cancel:"))
async def handle_cancel_registration(callback: CallbackQuery, config: Config) -> None:
    """Handle cancel button click from broadcast message."""
    event_id = int(callback.data.split(":")[1])

    event = Event.get_or_none(Event.id == event_id)
    if not event:
        await callback.answer("Event not found")
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


# --- Admin Handlers ---


def admin_check(config: Config):
    """Create filter for admin commands."""

    async def check(message: Message) -> bool:
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
        code = slugify(data["title"])
        event = Event.create(
            title=data["title"],
            description=data["description"],
            datetime_text=data["datetime_text"],
            code=code,
        )
        await state.clear()

        bot_info = await bot.get_me()
        link = f"https://t.me/{bot_info.username}?start={code}"
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
        code = slugify(data["title"])
        event = Event.create(
            title=data["title"],
            description=data["description"],
            datetime_text=data["datetime_text"],
            code=code,
            custom_question=data["custom_question"],
            question_type="text",
        )
        await state.clear()

        bot_info = await bot.get_me()
        link = f"https://t.me/{bot_info.username}?start={code}"
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
    code = slugify(data["title"])
    event = Event.create(
        title=data["title"],
        description=data["description"],
        datetime_text=data["datetime_text"],
        code=code,
        custom_question=data["custom_question"],
        question_type="options",
        question_options=message.text,
    )
    await state.clear()

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={code}"
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
    """Archive current active event."""
    if not config.is_admin_context(message.chat.id, message.from_user.id):
        return

    event = Event.get_active()
    if not event:
        await message.answer("No active event to end.")
        return

    event.is_active = False
    event.archived_at = utcnow()
    event.save()

    reg_count = (
        Registration.select()
        .where(
            Registration.event == event,
            Registration.cancelled == False,  # noqa: E712
        )
        .count()
    )

    await message.answer(
        f"✅ Event *{event.title}* archived.\n📊 Total registrations: {reg_count}",
        parse_mode="Markdown",
    )


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

    await state.update_data(broadcast_text=message.text)
    await state.set_state(BroadcastStates.confirm)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Send", callback_data="broadcast:send"),
                InlineKeyboardButton(
                    text="❌ Cancel", callback_data="broadcast:cancel"
                ),
            ]
        ]
    )
    await message.answer(
        f"📢 *Preview:*\n\n{message.text}\n\n_Confirm broadcast?_",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "broadcast:cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel broadcast."""
    await state.clear()
    await callback.message.edit_text("❌ Broadcast cancelled.")
    await callback.answer()


@router.callback_query(F.data == "broadcast:send")
async def send_broadcast(
    callback: CallbackQuery, config: Config, state: FSMContext, bot: Bot
) -> None:
    """Send broadcast to all registrants."""
    data = await state.get_data()
    event = Event.get_by_id(data["event_id"])
    broadcast_text = data["broadcast_text"]
    await state.clear()

    registrations = Registration.select().where(
        Registration.event == event,
        Registration.cancelled == False,  # noqa: E712
    )

    cancel_btn_text = get_event_message(event, "cancel_button_text", config)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=cancel_btn_text, callback_data=f"cancel:{event.id}"
                )
            ]
        ]
    )

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
    cancelled = total - active

    text = (
        f"📊 *Stats: {event.title}*\n\n"
        f"✅ Active: {active}\n"
        f"❌ Cancelled: {cancelled}\n"
        f"📋 Total: {total}"
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
        row = [
            reg.user.telegram_id,
            reg.user.username or "",
            reg.user.first_name or "",
            reg.user.last_name or "",
            reg.registered_at.isoformat(),
        ]
        if event.custom_question:
            row.append(reg.answer or "")
        writer.writerow(row)

    output.seek(0)
    from aiogram.types import BufferedInputFile

    file = BufferedInputFile(
        output.getvalue().encode("utf-8"), filename=f"{event.code}_registrations.csv"
    )
    await message.answer_document(file, caption=f"📋 Registrations for {event.title}")
