import pytest

from src.config import Config


def test_load_config(sample_config_file):
    config = Config.load(sample_config_file)

    assert config.admin_ids == [123456789, 987654321]
    assert config.admin_group_id == -1001234567890
    assert config.registration.no_active_event == "No events right now"
    assert config.event_defaults.cancel_button == "Cancel"


def test_is_admin(sample_config_file):
    config = Config.load(sample_config_file)

    assert config.is_admin(123456789) is True
    assert config.is_admin(987654321) is True
    assert config.is_admin(111111111) is False


def test_is_admin_context_group(sample_config_file):
    config = Config.load(sample_config_file)

    # Admin in correct group
    assert config.is_admin_context(-1001234567890, 123456789) is True

    # Admin in wrong group
    assert config.is_admin_context(-1009999999999, 123456789) is False

    # Non-admin in correct group
    assert config.is_admin_context(-1001234567890, 111111111) is False


def test_is_admin_context_dm(tmp_path):
    config_content = """
[bot]
admin_ids = [123456789]

[commands]
start = "Register"
newevent = "Create event"
endevent = "End event"
broadcast = "Broadcast"
stats = "Stats"
export = "Export"
history = "History"
broadcasts = "View broadcast history"
visualize = "Visualize"
version = "Show bot version"
dbexport = "Export database"

[registration]
no_active_event = "No events"
event_not_available = "Closed"
event_already_ended = "Event ended"
event_ended_notification = "Event concluded"
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
success = "Done {url}"
local_success = "Saved {path}"
no_events = "No events"

[dbexport]
generating = "Generating..."
success = "Done! Tables: {tables}, Rows: {rows}"
error = "Error: {error}"

[event_defaults]
registration_success = "Done"
already_registered = "Already"
confirm_button = "Coming!"
confirm_message = "See you!"
cancel_button = "Cancel"
cancel_message = "Cancelled"
"""
    config_path = tmp_path / "config.toml"
    config_path.write_text(config_content)
    config = Config.load(config_path)

    # Admin in DM
    assert config.is_admin_context(123456789, 123456789) is True

    # Admin in group
    assert config.is_admin_context(-1001234567890, 123456789) is False


def test_admin_command_descriptions(sample_config_file):
    config = Config.load(sample_config_file)

    assert config.commands.newevent == "Create a new event"
    assert config.commands.endevent == "End current event"
    assert config.commands.broadcast == "Send message to registrants"
    assert config.commands.stats == "View registration statistics"
    assert config.commands.export == "Export registrations to CSV"
    assert config.commands.history == "View past events"


def test_config_file_not_found():
    from pathlib import Path

    with pytest.raises(FileNotFoundError):
        Config.load(Path("/nonexistent/config.toml"))
