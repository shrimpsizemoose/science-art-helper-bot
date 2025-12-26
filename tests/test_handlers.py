from src.handlers import (
    generate_event_csv,
    get_event_stats,
    is_valid_event_code,
    suggest_event_code,
)
from src.models import Registration


def test_suggest_event_code_simple():
    assert suggest_event_code("Hello World") == "hello_world"


def test_suggest_event_code_special_chars():
    assert suggest_event_code("Python Workshop!!! 2025") == "python_workshop_2025"


def test_suggest_event_code_cyrillic_generates_hash():
    # Cyrillic-only title should generate a hash fallback
    result = suggest_event_code("Воркшоп")
    assert len(result) == 12  # md5 hex[:12]
    assert is_valid_event_code(result)


def test_suggest_event_code_mixed_keeps_ascii():
    # Mixed title keeps ASCII parts
    assert suggest_event_code("Воркшоп Python 2025") == "python_2025"


def test_suggest_event_code_long():
    long_title = (
        "This is a very long title that should be truncated to fifty characters"
    )
    result = suggest_event_code(long_title)
    assert len(result) <= 50


def test_suggest_event_code_multiple_spaces():
    assert suggest_event_code("Hello    World") == "hello_world"


def test_suggest_event_code_leading_trailing():
    assert suggest_event_code("  Hello World  ") == "hello_world"


def test_is_valid_event_code_valid():
    assert is_valid_event_code("hello_world") is True
    assert is_valid_event_code("event2025") is True
    assert is_valid_event_code("my_event_123") is True


def test_is_valid_event_code_invalid():
    assert is_valid_event_code("Hello World") is False  # spaces
    assert is_valid_event_code("event-2025") is False  # hyphen
    assert is_valid_event_code("Воркшоп") is False  # cyrillic
    assert is_valid_event_code("EVENT") is False  # uppercase
    assert is_valid_event_code("") is False  # empty


def test_is_valid_event_code_length():
    # 64 chars is max
    assert is_valid_event_code("a" * 64) is True
    assert is_valid_event_code("a" * 65) is False


# --- Helper function tests ---


def test_get_event_stats_empty(sample_event):
    stats = get_event_stats(sample_event)

    assert stats["registered"] == 0
    assert stats["confirmed"] == 0
    assert stats["cancelled"] == 0
    assert stats["pending"] == 0


def test_get_event_stats_with_registrations(sample_event, sample_user, temp_db):
    from src.models import User

    # Create additional users
    user2 = User.create(telegram_id=222, username="user2", first_name="User", last_name="Two")
    user3 = User.create(telegram_id=333, username="user3", first_name="User", last_name="Three")

    # Create registrations with different states
    Registration.create(user=sample_user, event=sample_event)  # active, not confirmed
    _ = Registration.create(user=user2, event=sample_event, confirmed=True)  # confirmed
    _ = Registration.create(user=user3, event=sample_event, cancelled=True)  # cancelled

    stats = get_event_stats(sample_event)

    assert stats["registered"] == 2  # active (not cancelled)
    assert stats["confirmed"] == 1
    assert stats["cancelled"] == 1
    assert stats["pending"] == 1  # registered but not confirmed


def test_generate_event_csv_empty(sample_event):
    output = generate_event_csv(sample_event)
    content = output.getvalue()

    # Should have header row only
    lines = content.strip().split("\n")
    assert len(lines) == 1
    assert "telegram_id" in lines[0]
    assert "answer" in lines[0]  # sample_event has custom_question


def test_generate_event_csv_with_registrations(sample_event, sample_user):
    Registration.create(user=sample_user, event=sample_event, answer="Beginner")

    output = generate_event_csv(sample_event)
    content = output.getvalue()

    lines = content.strip().split("\n")
    assert len(lines) == 2  # header + 1 registration

    # Check data row contains user info
    assert "111222333" in lines[1]  # telegram_id from sample_user
    assert "testuser" in lines[1]
    assert "Beginner" in lines[1]


def test_generate_event_csv_excludes_cancelled(sample_event, sample_user, temp_db):
    from src.models import User

    user2 = User.create(telegram_id=444, username="cancelled_user", first_name="Gone", last_name="User")

    Registration.create(user=sample_user, event=sample_event, answer="Beginner")
    Registration.create(user=user2, event=sample_event, answer="Advanced", cancelled=True)

    output = generate_event_csv(sample_event)
    content = output.getvalue()

    lines = content.strip().split("\n")
    assert len(lines) == 2  # header + 1 active registration
    assert "cancelled_user" not in content
