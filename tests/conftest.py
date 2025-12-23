import tempfile
from pathlib import Path

import pytest

from src.models import Event, User, db, init_db


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
register_button_text = "Register"
question_intro = "Quick question:"
skip_question_button_text = "Skip"

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
