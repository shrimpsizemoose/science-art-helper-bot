import sqlite3
from pathlib import Path

from src.db_export import generate_sqlite_export
from src.models import Broadcast, Event, Registration, User


def test_generate_sqlite_export_empty(temp_db):
    """Empty database produces valid SQLite with schema but no data."""
    export_path, stats = generate_sqlite_export()

    assert export_path.exists()
    assert stats["tables"] == 4
    assert stats["rows"] == 0

    # Verify it's a valid SQLite database with tables
    conn = sqlite3.connect(export_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()

    assert "user" in tables
    assert "event" in tables
    assert "registration" in tables
    assert "broadcast" in tables

    export_path.unlink()


def test_generate_sqlite_export_with_data(temp_db):
    """Data is correctly copied to export database."""
    user = User.create(telegram_id=123, username="alice", first_name="Alice")
    event = Event.create(
        title="Test Event",
        description="Description",
        datetime_text="Tomorrow",
        code="test_event",
    )
    Registration.create(user=user, event=event, answer="Yes")
    Broadcast.create(event=event, message_text="Hello!", target_audience="all")

    export_path, stats = generate_sqlite_export()

    assert stats["tables"] == 4
    assert stats["rows"] == 4  # 1 user + 1 event + 1 registration + 1 broadcast

    # Verify data in exported database
    conn = sqlite3.connect(export_path)
    cursor = conn.cursor()

    cursor.execute("SELECT telegram_id, username FROM user")
    users = cursor.fetchall()
    assert len(users) == 1
    assert users[0][0] == 123
    assert users[0][1] == "alice"

    cursor.execute("SELECT title, code FROM event")
    events = cursor.fetchall()
    assert len(events) == 1
    assert events[0][0] == "Test Event"
    assert events[0][1] == "test_event"

    cursor.execute("SELECT answer FROM registration")
    regs = cursor.fetchall()
    assert len(regs) == 1
    assert regs[0][0] == "Yes"

    cursor.execute("SELECT message_text FROM broadcast")
    broadcasts = cursor.fetchall()
    assert len(broadcasts) == 1
    assert broadcasts[0][0] == "Hello!"

    conn.close()
    export_path.unlink()


def test_generate_sqlite_export_stats_accuracy(temp_db):
    """Stats accurately reflect number of rows."""
    for i in range(5):
        User.create(telegram_id=i, username=f"user{i}")
    for i in range(3):
        Event.create(
            title=f"Event {i}",
            description="Desc",
            datetime_text="Now",
            code=f"event_{i}",
        )

    export_path, stats = generate_sqlite_export()

    assert stats["tables"] == 4
    assert stats["rows"] == 8  # 5 users + 3 events

    export_path.unlink()


def test_sqlite_export_cleanup_responsibility(temp_db):
    """Verify export returns a path that caller can clean up."""
    export_path, _ = generate_sqlite_export()

    assert isinstance(export_path, Path)
    assert export_path.exists()

    # Caller is responsible for cleanup
    export_path.unlink()
    assert not export_path.exists()


def test_generate_sqlite_export_unicode_data(temp_db):
    """Unicode characters are preserved in export."""
    User.create(telegram_id=1, first_name="Алексей", last_name="Петров")
    Event.create(
        title="Мастер-класс по живописи",
        description="Описание на русском языке",
        datetime_text="Завтра",
        code="unicode_event",
    )

    export_path, _ = generate_sqlite_export()

    conn = sqlite3.connect(export_path)
    cursor = conn.cursor()

    cursor.execute("SELECT first_name, last_name FROM user")
    user = cursor.fetchone()
    assert user[0] == "Алексей"
    assert user[1] == "Петров"

    cursor.execute("SELECT title, description FROM event")
    event = cursor.fetchone()
    assert event[0] == "Мастер-класс по живописи"
    assert event[1] == "Описание на русском языке"

    conn.close()
    export_path.unlink()


def test_generate_sqlite_export_null_values(temp_db):
    """NULL values are preserved in export."""
    User.create(telegram_id=1, username=None, first_name=None, last_name=None)
    Event.create(
        title="Minimal Event",
        description="Desc",
        datetime_text="Now",
        code="minimal",
        custom_question=None,
        question_type=None,
    )

    export_path, _ = generate_sqlite_export()

    conn = sqlite3.connect(export_path)
    cursor = conn.cursor()

    cursor.execute("SELECT username, first_name, last_name FROM user")
    user = cursor.fetchone()
    assert user == (None, None, None)

    cursor.execute("SELECT custom_question, question_type FROM event")
    event = cursor.fetchone()
    assert event == (None, None)

    conn.close()
    export_path.unlink()
