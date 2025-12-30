import pytest

from src.config import Config


def test_load_config(sample_config_file):
    config = Config.load(sample_config_file)

    assert config.admin_ids == [123456789, 987654321]
    assert config.admin_group_id == -1001234567890
    assert config.system_messages.no_active_event == "No events right now"
    assert config.default_event_messages.cancel_button_text == "Cancel"


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

[system_messages]
no_active_event = "No events"
event_not_available = "Closed"
event_already_ended = "Event ended"
event_ended_notification = "Event concluded"
register_button_text = "Register"
question_intro = "Quick question:"
skip_question_button_text = "Skip"
unknown_message = "Use /start to register."
start_command_description = "Register"
newevent_command_description = "Create event"
endevent_command_description = "End event"
broadcast_command_description = "Broadcast"
stats_command_description = "Stats"
export_command_description = "Export"
history_command_description = "History"
history_broadcast_intro = "Broadcast to {event_title}. Recipients: {count}"
broadcasts_command_description = "View broadcast history"
no_broadcasts = "No broadcasts have been sent yet."
broadcast_history_header = "Broadcast History for {event_title}"
visualize_command_description = "Visualize"
version_command_description = "Show bot version"
visualization_success = "Done {url}"
visualization_local_success = "Saved {path}"
visualization_generating = "Generating..."
visualization_no_events = "No events"
end_broadcast_intro = "Broadcast to {event_title}. Recipients: {count}. Template: {template}"
dbexport_command_description = "Export database"
dbexport_generating = "Generating..."
dbexport_success = "Done! Tables: {tables}, Rows: {rows}"
dbexport_error = "Error: {error}"

[default_event_messages]
registration_success = "Done"
already_registered = "Already"
confirm_button_text = "Coming!"
confirm_confirmation = "See you!"
cancel_button_text = "Cancel"
cancel_confirmation = "Cancelled"
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

    assert config.system_messages.newevent_command_description == "Create a new event"
    assert config.system_messages.endevent_command_description == "End current event"
    assert config.system_messages.broadcast_command_description == "Send message to registrants"
    assert config.system_messages.stats_command_description == "View registration statistics"
    assert config.system_messages.export_command_description == "Export registrations to CSV"
    assert config.system_messages.history_command_description == "View past events"


def test_config_file_not_found():
    from pathlib import Path

    with pytest.raises(FileNotFoundError):
        Config.load(Path("/nonexistent/config.toml"))
