from datetime import UTC, datetime
from urllib.parse import urlparse

from peewee import (
    AutoField,
    BigIntegerField,
    BooleanField,
    CharField,
    DatabaseProxy,
    DateTimeField,
    ForeignKeyField,
    Model,
    PostgresqlDatabase,
    SqliteDatabase,
    TextField,
)


def utcnow():
    return datetime.now(UTC)


# Deferred database - will be initialized at runtime
db = DatabaseProxy()


class BaseModel(Model):
    id = AutoField()

    class Meta:
        database = db


class User(BaseModel):
    """Telegram user that interacts with the bot."""

    telegram_id = BigIntegerField(unique=True)
    username = CharField(null=True)
    first_name = CharField(null=True)
    last_name = CharField(null=True)
    created_at = DateTimeField(default=utcnow)

    @property
    def display_name(self) -> str:
        if self.first_name:
            name = self.first_name
            if self.last_name:
                name += f" {self.last_name}"
            return name
        return self.username or str(self.telegram_id)


class Event(BaseModel):
    """Workshop/webinar event."""

    title = CharField()
    description = TextField()
    datetime_text = CharField()  # Free-form datetime string
    code = CharField(unique=True)  # For deep links: t.me/bot?start=<code>

    # Custom question (optional)
    custom_question = TextField(null=True)
    question_type = CharField(null=True)  # 'text' or 'options'
    question_options = TextField(null=True)  # Comma-separated options

    # Event messages (overrides defaults from config if set)
    msg_registration_success = TextField(null=True)
    msg_already_registered = TextField(null=True)
    msg_cancel_button_text = TextField(null=True)
    msg_cancel_confirmation = TextField(null=True)

    is_active = BooleanField(default=True)
    confirmation_sent = BooleanField(default=False)
    confirmation_sent_at = DateTimeField(null=True)
    created_at = DateTimeField(default=utcnow)
    archived_at = DateTimeField(null=True)

    @classmethod
    def get_active(cls) -> "Event | None":
        return cls.select().where(cls.is_active == True).first()  # noqa: E712

    def get_options_list(self) -> list[str]:
        if self.question_options:
            return [opt.strip() for opt in self.question_options.split(",")]
        return []


class Registration(BaseModel):
    """User registration for an event."""

    user = ForeignKeyField(User, backref="registrations")
    event = ForeignKeyField(Event, backref="registrations")
    answer = TextField(null=True)  # Answer to custom question
    registered_at = DateTimeField(default=utcnow)
    confirmed = BooleanField(default=False)
    confirmed_at = DateTimeField(null=True)
    cancelled = BooleanField(default=False)
    cancelled_at = DateTimeField(null=True)

    class Meta:
        indexes = ((("user", "event"), True),)  # Unique together


class Broadcast(BaseModel):
    """Record of a broadcast message sent to event registrants."""

    event = ForeignKeyField(Event, backref="broadcasts")
    message_text = TextField()
    target_audience = CharField()  # 'all' or 'non_responders'
    include_buttons = BooleanField(default=False)
    sent_count = BigIntegerField(default=0)
    failed_count = BigIntegerField(default=0)
    sent_at = DateTimeField(default=utcnow)


def init_db(database_url: str) -> None:
    """Initialize database connection and create tables."""
    parsed = urlparse(database_url)

    if parsed.scheme == "sqlite":
        db_path = database_url.replace("sqlite:///", "")
        database = SqliteDatabase(db_path)
    elif parsed.scheme in ("postgres", "postgresql"):
        database = PostgresqlDatabase(
            parsed.path[1:],  # Remove leading /
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port or 5432,
        )
    else:
        raise ValueError(f"Unsupported database scheme: {parsed.scheme}")

    db.initialize(database)
    db.connect(reuse_if_open=True)
    db.create_tables([User, Event, Registration, Broadcast])
