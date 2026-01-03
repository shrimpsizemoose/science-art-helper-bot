import sqlite3

from src.db_export import generate_sqlite_export
from src.models import Broadcast, Event, Registration, User


def _load_export_db(db_bytes: bytes) -> sqlite3.Connection:
    """Load exported bytes into a sqlite3 connection for testing."""
    conn = sqlite3.connect(":memory:")
    conn.deserialize(db_bytes)
    return conn


def test_generate_sqlite_export_empty(temp_db):
    db_bytes, stats = generate_sqlite_export()

    assert isinstance(db_bytes, bytes)
    assert len(db_bytes) > 0
    assert stats["tables"] == 4
    assert stats["rows"] == 0

    conn = _load_export_db(db_bytes)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()

    assert "user" in tables
    assert "event" in tables
    assert "registration" in tables
    assert "broadcast" in tables


def test_generate_sqlite_export_with_data(temp_db):
    user = User.create(telegram_id=123, username="alice", first_name="Alice")
    event = Event.create(
        title="Test Event",
        description="Description",
        datetime_text="Tomorrow",
        code="test_event",
    )
    Registration.create(user=user, event=event, answer="Yes")
    Broadcast.create(event=event, message_text="Hello!", target_audience="all")

    db_bytes, stats = generate_sqlite_export()

    assert stats["tables"] == 4
    assert stats["rows"] == 4

    conn = _load_export_db(db_bytes)
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


def test_generate_sqlite_export_stats_accuracy(temp_db):
    for i in range(5):
        User.create(telegram_id=i, username=f"user{i}")
    for i in range(3):
        Event.create(
            title=f"Event {i}",
            description="Desc",
            datetime_text="Now",
            code=f"event_{i}",
        )

    db_bytes, stats = generate_sqlite_export()

    assert stats["tables"] == 4
    assert stats["rows"] == 8


def test_generate_sqlite_export_returns_bytes(temp_db):
    db_bytes, _ = generate_sqlite_export()

    assert isinstance(db_bytes, bytes)
    assert len(db_bytes) > 0
    # SQLite files start with "SQLite format 3\x00"
    assert db_bytes[:16] == b"SQLite format 3\x00"


def test_generate_sqlite_export_unicode_data(temp_db):
    User.create(telegram_id=1, first_name="Алексей", last_name="Петров")
    Event.create(
        title="Мастер-класс по живописи",
        description="Описание на русском языке",
        datetime_text="Завтра",
        code="unicode_event",
    )

    db_bytes, _ = generate_sqlite_export()

    conn = _load_export_db(db_bytes)
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


def test_generate_sqlite_export_null_values(temp_db):
    User.create(telegram_id=1, username=None, first_name=None, last_name=None)
    Event.create(
        title="Minimal Event",
        description="Desc",
        datetime_text="Now",
        code="minimal",
        custom_question=None,
        question_type=None,
    )

    db_bytes, _ = generate_sqlite_export()

    conn = _load_export_db(db_bytes)
    cursor = conn.cursor()

    cursor.execute("SELECT username, first_name, last_name FROM user")
    user = cursor.fetchone()
    assert user == (None, None, None)

    cursor.execute("SELECT custom_question, question_type FROM event")
    event = cursor.fetchone()
    assert event == (None, None)

    conn.close()
