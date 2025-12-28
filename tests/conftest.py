import tempfile
from pathlib import Path

import pytest

from src.models import Broadcast, Event, User, db, init_db


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    init_db(f"sqlite:///{db_path}")
    yield db

    db.close()
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def sample_config_file(tmp_path):
    config_content = """
[bot]
admin_ids = [123456789, 987654321]
admin_group_id = -1001234567890

[system_messages]
no_active_event = "No events right now"
event_not_available = "Event closed"
event_already_ended = "This event has already ended."
event_ended_notification = "{event_title} has concluded."
register_button_text = "Register"
question_intro = "Quick question:"
skip_question_button_text = "Skip"
unknown_message = "Use /start to register."
start_command_description = "Register"
newevent_command_description = "Create a new event"
endevent_command_description = "End current event"
broadcast_command_description = "Send message to registrants"
stats_command_description = "View registration statistics"
export_command_description = "Export registrations to CSV"
history_command_description = "View past events"
history_broadcast_intro = "Broadcast to {event_title}. Recipients: {count}"
broadcasts_command_description = "View broadcast history"
no_broadcasts = "No broadcasts have been sent yet."
broadcast_history_header = "Broadcast History for {event_title}"
visualize_command_description = "Generate event visualization"
version_command_description = "Show bot version"
visualization_success = "Visualization generated! {url}"
visualization_local_success = "Visualization saved: {path}"
visualization_generating = "Generating..."
visualization_no_events = "No events to visualize"
end_broadcast_intro = "Broadcast to {event_title}. Recipients: {count}. Template: {template}"

[default_event_messages]
registration_success = "Registered for {event_title}!"
already_registered = "Already in {event_title}"
confirm_button_text = "I'll be there!"
confirm_confirmation = "See you at {event_title}!"
cancel_button_text = "Cancel"
cancel_confirmation = "Cancelled from {event_title}"
"""
    config_path = tmp_path / "config.toml"
    config_path.write_text(config_content)
    return config_path


@pytest.fixture
def sample_user(temp_db):
    return User.create(
        telegram_id=111222333,
        username="testuser",
        first_name="Test",
        last_name="User",
    )


@pytest.fixture
def sample_event(temp_db):
    return Event.create(
        title="Test Workshop",
        description="A test workshop",
        datetime_text="January 1, 2025 at 10am",
        code="test_workshop",
        custom_question="What's your level?",
        question_type="options",
        question_options="Beginner, Intermediate, Advanced",
    )


@pytest.fixture
def sample_broadcast(sample_event):
    return Broadcast.create(
        event=sample_event,
        message_text="Hello everyone! Reminder about the workshop.",
        target_audience="all",
        include_buttons=True,
        sent_count=10,
        failed_count=2,
    )
