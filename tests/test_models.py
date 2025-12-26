from src.models import Broadcast, Event, Registration, User, utcnow


def test_user_display_name_full(sample_user):
    assert sample_user.display_name == "Test User"


def test_user_display_name_first_only(temp_db):
    user = User.create(telegram_id=1, first_name="Alice")
    assert user.display_name == "Alice"


def test_user_display_name_username_fallback(temp_db):
    user = User.create(telegram_id=2, username="alice_bob")
    assert user.display_name == "alice_bob"


def test_user_display_name_id_fallback(temp_db):
    user = User.create(telegram_id=3)
    assert user.display_name == "3"


def test_event_get_active(sample_event):
    active = Event.get_active()
    assert active is not None
    assert active.id == sample_event.id


def test_event_get_active_none(temp_db):
    assert Event.get_active() is None


def test_event_get_active_archived(sample_event):
    sample_event.is_active = False
    sample_event.save()

    assert Event.get_active() is None


def test_event_get_options_list(sample_event):
    options = sample_event.get_options_list()
    assert options == ["Beginner", "Intermediate", "Advanced"]


def test_event_get_options_list_empty(temp_db):
    event = Event.create(
        title="No Question Event",
        description="Test",
        datetime_text="Now",
        code="no_question",
    )
    assert event.get_options_list() == []


def test_registration_create(sample_user, sample_event):
    reg = Registration.create(
        user=sample_user,
        event=sample_event,
        answer="Beginner",
    )

    assert reg.user.telegram_id == sample_user.telegram_id
    assert reg.event.id == sample_event.id
    assert reg.answer == "Beginner"
    assert reg.cancelled is False


def test_registration_cancel(sample_user, sample_event):
    reg = Registration.create(user=sample_user, event=sample_event)
    reg.cancelled = True
    reg.cancelled_at = utcnow()
    reg.save()

    reg_reloaded = Registration.get_by_id(reg.id)
    assert reg_reloaded.cancelled is True
    assert reg_reloaded.cancelled_at is not None


def test_broadcast_create(sample_event):
    bc = Broadcast.create(
        event=sample_event,
        message_text="Test broadcast message",
        target_audience="all",
        include_buttons=True,
        sent_count=5,
        failed_count=1,
    )

    assert bc.event.id == sample_event.id
    assert bc.message_text == "Test broadcast message"
    assert bc.target_audience == "all"
    assert bc.include_buttons is True
    assert bc.sent_count == 5
    assert bc.failed_count == 1
    assert bc.sent_at is not None


def test_broadcast_non_responders_audience(sample_event):
    bc = Broadcast.create(
        event=sample_event,
        message_text="Reminder for non-responders",
        target_audience="non_responders",
        include_buttons=False,
        sent_count=3,
        failed_count=0,
    )

    assert bc.target_audience == "non_responders"
    assert bc.include_buttons is False


def test_broadcast_backref(sample_event):
    Broadcast.create(
        event=sample_event,
        message_text="First broadcast",
        target_audience="all",
    )
    Broadcast.create(
        event=sample_event,
        message_text="Second broadcast",
        target_audience="non_responders",
    )

    broadcasts = list(sample_event.broadcasts)
    assert len(broadcasts) == 2
    messages = [bc.message_text for bc in broadcasts]
    assert "First broadcast" in messages
    assert "Second broadcast" in messages
