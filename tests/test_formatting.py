"""Tests for formatting functions."""

from src.formatting import (
    build_broadcast_buttons,
    format_endevent_result,
    format_event_created,
    format_event_info,
    format_history_list,
    format_stats_message,
)


class TestFormatEventInfo:
    def test_basic(self):
        result = format_event_info("Test Event", "A description", "Jan 1, 2025")
        assert "📋 *Test Event*" in result
        assert "A description" in result
        assert "📅 Jan 1, 2025" in result
        assert result.count("\n\n") == 2

    def test_multiline_description(self):
        result = format_event_info("Event", "Line 1\nLine 2", "Tomorrow")
        assert "Line 1\nLine 2" in result


class TestFormatStatsMessage:
    def test_basic_stats(self):
        stats = {"confirmed": 5, "registered": 10, "cancelled": 2}
        result = format_stats_message("My Event", stats)

        assert "📊 *Stats: My Event*" in result
        assert "🎉 Confirmed: 5" in result
        assert "📋 Registered: 10" in result
        assert "❌ Cancelled: 2" in result

    def test_with_options(self):
        stats = {"confirmed": 5, "registered": 10, "cancelled": 2}
        options = ["Beginner", "Advanced"]
        answer_counts = {"Beginner": 6, "Advanced": 4}

        result = format_stats_message("Event", stats, options, answer_counts)

        assert "*Answers:*" in result
        assert "• Beginner: 6" in result
        assert "• Advanced: 4" in result

    def test_with_options_missing_count(self):
        stats = {"confirmed": 0, "registered": 0, "cancelled": 0}
        options = ["A", "B"]
        answer_counts = {"A": 1}  # B is missing

        result = format_stats_message("Event", stats, options, answer_counts)

        assert "• A: 1" in result
        assert "• B: 0" in result  # defaults to 0


class TestBuildBroadcastButtons:
    def test_first_broadcast(self):
        buttons, prompt = build_broadcast_buttons(
            all_count=10,
            non_responders_count=10,
            confirmation_sent=False,
        )

        assert "_Include participation confirmation buttons?_" in prompt
        assert len(buttons) == 3  # confirm buttons, no buttons, cancel

        # Check button texts
        button_texts = [btn.text for row in buttons for btn in row]
        assert "✅ Include participation confirmation buttons" in button_texts
        assert "📤 Send without buttons" in button_texts
        assert "❌ Cancel" in button_texts

    def test_confirmation_already_sent(self):
        buttons, prompt = build_broadcast_buttons(
            all_count=10,
            non_responders_count=5,
            confirmation_sent=True,
        )

        assert "_Confirmation was already sent" in prompt
        assert len(buttons) == 3  # all, non-responders, cancel

        button_texts = [btn.text for row in buttons for btn in row]
        assert "📤 Send to all (10)" in button_texts
        assert "🎯 Send to non-responders (5) + buttons" in button_texts

    def test_confirmation_sent_all_responded(self):
        # When everyone has responded, no non-responders button
        buttons, prompt = build_broadcast_buttons(
            all_count=10,
            non_responders_count=0,
            confirmation_sent=True,
        )

        assert len(buttons) == 2  # all, cancel (no non-responders)
        button_texts = [btn.text for row in buttons for btn in row]
        assert "📤 Send to all (10)" in button_texts
        assert not any("non-responders" in t for t in button_texts)

    def test_confirmation_sent_all_non_responders(self):
        # When no one has responded, no separate non-responders button
        buttons, prompt = build_broadcast_buttons(
            all_count=10,
            non_responders_count=10,
            confirmation_sent=True,
        )

        assert len(buttons) == 2  # all, cancel
        button_texts = [btn.text for row in buttons for btn in row]
        assert not any("non-responders" in t for t in button_texts)


class TestFormatEndeventResult:
    def test_silent_end(self):
        stats = {"registered": 10, "confirmed": 8, "cancelled": 2}
        result = format_endevent_result("My Event", stats, notify=False)

        assert '✅ *Event "My Event" archived.*' in result
        assert "Registered: 10" in result
        assert "Confirmed: 8" in result
        assert "Cancelled: 2" in result
        assert "Notifications sent" not in result
        assert "/history" in result

    def test_with_notifications(self):
        stats = {"registered": 10, "confirmed": 8, "cancelled": 2}
        result = format_endevent_result("Event", stats, notify=True, sent=8, failed=0)

        assert "📤 Notifications sent: 8" in result
        assert "failed" not in result

    def test_with_failed_notifications(self):
        stats = {"registered": 10, "confirmed": 8, "cancelled": 2}
        result = format_endevent_result("Event", stats, notify=True, sent=6, failed=2)

        assert "📤 Notifications sent: 6" in result
        assert "(failed: 2)" in result


class TestFormatHistoryList:
    def test_single_event(self):
        events = [
            (1, "Workshop 1", "Dec 25, 2024", {"registered": 10, "confirmed": 8}),
        ]
        text, buttons = format_history_list(events)

        assert "📜 *Past Events:*" in text
        assert "*1. Workshop 1*" in text
        assert "Dec 25, 2024" in text
        assert "Registered: 10" in text
        assert "Confirmed: 8" in text
        assert len(buttons) == 1
        assert buttons[0].callback_data == "history:export:1"

    def test_multiple_events(self):
        events = [
            (1, "Event A", "Dec 1", {"registered": 5, "confirmed": 3}),
            (2, "Event B", "Dec 15", {"registered": 20, "confirmed": 18}),
        ]
        text, buttons = format_history_list(events)

        assert "*1. Event A*" in text
        assert "*2. Event B*" in text
        assert len(buttons) == 2
        assert buttons[0].text == "📤 #1"
        assert buttons[1].text == "📤 #2"


class TestFormatEventCreated:
    def test_basic(self):
        result = format_event_created("My Event", "https://t.me/bot?start=code")

        assert "✅ *Event created!*" in result
        assert "📋 My Event" in result
        assert "`https://t.me/bot?start=code`" in result
        assert "Question" not in result
        assert "Options" not in result

    def test_with_question(self):
        result = format_event_created(
            "Event",
            "https://t.me/bot?start=x",
            custom_question="What's your level?",
        )

        assert "❓ Question: What's your level?" in result
        assert "Options" not in result

    def test_with_options(self):
        result = format_event_created(
            "Event",
            "https://t.me/bot?start=x",
            custom_question="Level?",
            options=["Beginner", "Pro"],
        )

        assert "❓ Question: Level?" in result
        assert "📝 Options: Beginner, Pro" in result
