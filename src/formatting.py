from aiogram.types import InlineKeyboardButton


def format_event_info(title: str, description: str, datetime_text: str) -> str:
    return "\n\n".join([
        f"📋 *{title}*",
        description,
        f"📅 {datetime_text}",
    ])


def format_stats_message(
    event_title: str,
    stats: dict,
    options: list[str] | None = None,
    answer_counts: dict[str, int] | None = None,
) -> str:
    text = "\n\n".join([
        f"📊 *Stats: {event_title}*",
        "\n".join([
            f"🎉 Confirmed: {stats['confirmed']}",
            f"📋 Registered: {stats['registered']}",
            f"❌ Cancelled: {stats['cancelled']}",
        ]),
    ])

    if options and answer_counts is not None:
        text += "\n\n*Answers:*"
        for opt in options:
            count = answer_counts.get(opt, 0)
            text += f"\n• {opt}: {count}"

    return text


def build_broadcast_buttons(
    all_count: int,
    non_responders_count: int,
    confirmation_sent: bool,
) -> tuple[list[list[InlineKeyboardButton]], str]:
    """Returns (button_rows, prompt_text)."""
    buttons = []

    if confirmation_sent:
        buttons.append([
            InlineKeyboardButton(
                text=f"📤 Send to all ({all_count})",
                callback_data="broadcast:send:no_buttons:all",
            ),
        ])
        if non_responders_count > 0 and non_responders_count < all_count:
            buttons.append([
                InlineKeyboardButton(
                    text=f"🎯 Send to non-responders ({non_responders_count}) + buttons",
                    callback_data="broadcast:send:buttons:non_responders",
                ),
            ])
        prompt = "_Confirmation was already sent. Choose recipients:_"
    else:
        buttons.append([
            InlineKeyboardButton(
                text="✅ Include participation confirmation buttons",
                callback_data="broadcast:send:buttons:all",
            ),
        ])
        buttons.append([
            InlineKeyboardButton(
                text="📤 Send without buttons",
                callback_data="broadcast:send:no_buttons:all",
            ),
        ])
        prompt = "_Include participation confirmation buttons?_"

    buttons.append([
        InlineKeyboardButton(text="❌ Cancel", callback_data="broadcast:cancel"),
    ])

    return buttons, prompt


def format_endevent_result(
    event_title: str,
    stats: dict,
    notify: bool,
    sent: int = 0,
    failed: int = 0,
) -> str:
    text = "\n\n".join([
        f'✅ *Event "{event_title}" archived.*',
        "\n".join([
            "📊 Final stats:",
            f"Registered: {stats['registered']}",
            f"Confirmed: {stats['confirmed']}",
            f"Cancelled: {stats['cancelled']}",
        ]),
    ])

    if notify:
        text += f"\n\n📤 Notifications sent: {sent}"
        if failed:
            text += f" (failed: {failed})"

    text += "\n\nUse /history to view past events."
    return text


def format_history_list(
    events: list[tuple[int, str, str, dict]],
) -> tuple[str, list[InlineKeyboardButton], list[InlineKeyboardButton]]:
    """Format history list with export and broadcast buttons.

    Args:
        events: list of (event_id, title, archived_date, stats)

    Returns:
        (text, export_buttons, broadcast_buttons)
    """
    text = "📜 *Past Events:*\n"
    export_buttons = []
    broadcast_buttons = []

    for i, (event_id, title, archived_date, stats) in enumerate(events, 1):
        text += (
            f"\n*{i}. {title}* ({archived_date})\n"
            f"   Registered: {stats['registered']} | Confirmed: {stats['confirmed']}\n"
        )
        export_buttons.append(
            InlineKeyboardButton(
                text=f"📤 #{i}", callback_data=f"history:export:{event_id}"
            )
        )
        broadcast_buttons.append(
            InlineKeyboardButton(
                text=f"📢 #{i}", callback_data=f"history:broadcast:{event_id}"
            )
        )

    return text, export_buttons, broadcast_buttons


def format_event_created(
    title: str,
    link: str,
    custom_question: str | None = None,
    options: list[str] | None = None,
) -> str:
    lines = [f"📋 {title}"]

    if custom_question:
        lines.append(f"❓ Question: {custom_question}")

    if options:
        lines.append(f"📝 Options: {', '.join(options)}")

    lines.append(f"🔗 Registration link:\n`{link}`")

    return "\n\n".join([
        "✅ *Event created!*",
        "\n".join(lines),
    ])
