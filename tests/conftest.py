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

[commands]
start = "Register"
newevent = "Create a new event"
endevent = "End current event"
broadcast = "Send message to registrants"
stats = "View registration statistics"
export = "Export registrations to CSV"
history = "View past events"
broadcasts = "View broadcast history"
visualize = "Generate event visualization"
version = "Show bot version"
dbexport = "Export database as SQLite"

[registration]
no_active_event = "No events right now"
event_not_available = "Event closed"
event_already_ended = "This event has already ended."
event_ended_notification = "{event_title} has concluded."
question_intro = "Quick question:"
unknown_message = "Use /start to register."
register_button = "Register"
skip_button = "Skip"

[broadcast]
history_intro = "Broadcast to {event_title}. Recipients: {count}"
no_history = "No broadcasts have been sent yet."
history_header = "Broadcast History for {event_title}"
end_event_intro = "Broadcast to {event_title}. Recipients: {count}. Template: {template}"

[visualization]
generating = "Generating..."
success = "Visualization generated! {url}"
local_success = "Visualization saved: {path}"
no_events = "No events to visualize"

[dbexport]
generating = "Generating SQLite export..."
success = "Database exported! Tables: {tables}, Rows: {rows}"
success_url = "Database exported! Tables: {tables}, Rows: {rows}, URL: {url}"
error = "Failed to export: {error}"

[event_defaults]
registration_success = "Registered for {event_title}!"
already_registered = "Already in {event_title}"
confirm_button = "I'll be there!"
confirm_message = "See you at {event_title}!"
cancel_button = "Cancel"
cancel_message = "Cancelled from {event_title}"
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
