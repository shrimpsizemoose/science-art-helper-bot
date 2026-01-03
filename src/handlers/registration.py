from aiogram import Bot, F
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.config import Config
from src.formatting import format_event_info
from src.handlers.helpers import get_event_message, get_or_create_user
from src.handlers.states import RegistrationStates
from src.models import Event, Registration, User, utcnow

from . import router


@router.message(CommandStart(deep_link=True))
async def cmd_start_with_code(
    message: Message, command: CommandObject, config: Config
) -> None:
    event_code = command.args
    event = (
        Event.select().where(Event.code == event_code, Event.is_active == True).first()  # noqa: E712
    )

    if not event:
        await message.answer(config.registration.event_not_available)
        return

    user = get_or_create_user(message.from_user)

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

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=config.registration.register_button,
                    callback_data=f"register:{event.id}",
                )
            ]
        ]
    )
    await message.answer(
        format_event_info(event.title, event.description, event.datetime_text),
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@router.message(CommandStart())
async def cmd_start(message: Message, config: Config) -> None:
    event = Event.get_active()

    if not event:
        await message.answer(config.registration.no_active_event)
        return

    user = get_or_create_user(message.from_user)

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

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=config.registration.register_button,
                    callback_data=f"register:{event.id}",
                )
            ]
        ]
    )
    await message.answer(
        format_event_info(event.title, event.description, event.datetime_text),
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("answer:"))
async def handle_option_answer(
    callback: CallbackQuery, config: Config, state: FSMContext
) -> None:
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
    message: Message,
    config: Config,
    state: FSMContext,
    bot: Bot,
) -> None:
    data = await state.get_data()

    event = Event.get_by_id(data["event_id"])
    user = User.get_by_id(data["user_id"])

    answer = None if message.text == "/skip" else message.text
    Registration.create(user=user, event=event, answer=answer)
    await state.clear()

    if "question_message_id" in data:
        try:
            await bot.edit_message_reply_markup(
                chat_id=data["question_chat_id"],
                message_id=data["question_message_id"],
                reply_markup=None,
            )
        except Exception:  # noqa: S110
            pass  # Message might be too old or deleted

    msg = get_event_message(event, "registration_success", config)
    await message.answer(
        f"✅ {msg.format(event_title=event.title, user_name=user.display_name)}"
    )


@router.callback_query(F.data == "answer_skip")
async def handle_skip_answer(
    callback: CallbackQuery, config: Config, state: FSMContext
) -> None:
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
    event_id = int(callback.data.split(":")[1])

    event = Event.get_or_none(Event.id == event_id)
    if not event:
        await callback.answer("Event not found")
        return

    if not event.is_active:
        await callback.answer(config.registration.event_already_ended, show_alert=True)
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

    msg = get_event_message(event, "confirm_message", config)
    await callback.message.edit_text(
        msg.format(event_title=event.title, user_name=user.display_name)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel:"))
async def handle_cancel_registration(callback: CallbackQuery, config: Config) -> None:
    event_id = int(callback.data.split(":")[1])

    event = Event.get_or_none(Event.id == event_id)
    if not event:
        await callback.answer("Event not found")
        return

    if not event.is_active:
        await callback.answer(config.registration.event_already_ended, show_alert=True)
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

    msg = get_event_message(event, "cancel_message", config)
    await callback.message.edit_text(
        msg.format(event_title=event.title, user_name=user.display_name)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("register:"))
async def handle_register_button(
    callback: CallbackQuery, config: Config, state: FSMContext
) -> None:
    event_id = int(callback.data.split(":")[1])

    event = Event.get_or_none(
        Event.id == event_id,
        Event.is_active == True,  # noqa: E712
    )
    if not event:
        await callback.answer(config.registration.event_not_available)
        return

    user = get_or_create_user(callback.from_user)

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
                            text=config.registration.skip_button,
                            callback_data="answer_skip",
                        )
                    ]
                ]
            )
            await callback.message.edit_text(
                "\n\n".join(
                    [
                        f"📋 *{event.title}*",
                        config.registration.question_intro,
                        event.custom_question,
                    ]
                ),
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        else:
            await state.set_state(RegistrationStates.answer)
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=config.registration.skip_button,
                            callback_data="answer_skip",
                        )
                    ]
                ]
            )
            await callback.message.edit_text(
                "\n\n".join(
                    [
                        f"📋 *{event.title}*",
                        config.registration.question_intro,
                        event.custom_question,
                    ]
                ),
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            await state.update_data(
                question_chat_id=callback.message.chat.id,
                question_message_id=callback.message.message_id,
            )
        await callback.answer()
        return

    Registration.create(user=user, event=event)
    msg = get_event_message(event, "registration_success", config)
    await callback.message.edit_text(
        f"✅ {msg.format(event_title=event.title, user_name=user.display_name)}"
    )
    await callback.answer()


@router.message()
async def handle_unknown_message(message: Message, config: Config) -> None:
    await message.answer(config.registration.unknown_message)
