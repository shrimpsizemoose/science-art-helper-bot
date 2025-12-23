from src.models import Event, Registration, User, utcnow


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
