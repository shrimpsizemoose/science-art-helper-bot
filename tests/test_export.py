import json

from src.export import generate_broadcasts_json
from src.models import Broadcast


def test_generate_broadcasts_json_empty(sample_event):
    """Test export with no broadcasts."""
    result = generate_broadcasts_json(sample_event)
    data = json.loads(result)

    assert data["event"]["id"] == sample_event.id
    assert data["event"]["title"] == sample_event.title
    assert data["event"]["code"] == sample_event.code
    assert data["broadcasts"] == []
    assert data["summary"]["total_broadcasts"] == 0
    assert data["summary"]["total_recipients_reached"] == 0


def test_generate_broadcasts_json_single(sample_broadcast):
    """Test export with a single broadcast."""
    event = sample_broadcast.event
    result = generate_broadcasts_json(event)
    data = json.loads(result)

    assert data["event"]["id"] == event.id
    assert len(data["broadcasts"]) == 1

    bc = data["broadcasts"][0]
    assert bc["message_text"] == sample_broadcast.message_text
    assert bc["target_audience"] == "all"
    assert bc["include_buttons"] is True
    assert bc["sent_count"] == 10
    assert bc["failed_count"] == 2

    assert data["summary"]["total_broadcasts"] == 1
    assert data["summary"]["total_recipients_reached"] == 10
    assert data["summary"]["total_failed_deliveries"] == 2


def test_generate_broadcasts_json_multiple(sample_event):
    """Test export with multiple broadcasts."""
    Broadcast.create(
        event=sample_event,
        message_text="First message",
        target_audience="all",
        include_buttons=True,
        sent_count=20,
        failed_count=5,
    )
    Broadcast.create(
        event=sample_event,
        message_text="Second message",
        target_audience="non_responders",
        include_buttons=False,
        sent_count=8,
        failed_count=1,
    )
    Broadcast.create(
        event=sample_event,
        message_text="Third message",
        target_audience="all",
        include_buttons=False,
        sent_count=15,
        failed_count=0,
    )

    result = generate_broadcasts_json(sample_event)
    data = json.loads(result)

    assert len(data["broadcasts"]) == 3
    assert data["summary"]["total_broadcasts"] == 3
    assert data["summary"]["total_recipients_reached"] == 20 + 8 + 15
    assert data["summary"]["total_failed_deliveries"] == 5 + 1 + 0


def test_generate_broadcasts_json_archived_event(sample_event):
    """Test export includes archived_at for archived events."""
    from src.models import utcnow

    sample_event.is_active = False
    sample_event.archived_at = utcnow()
    sample_event.save()

    result = generate_broadcasts_json(sample_event)
    data = json.loads(result)

    assert data["event"]["is_active"] is False
    assert data["event"]["archived_at"] is not None


def test_generate_broadcasts_json_valid_json(sample_broadcast):
    """Test that output is valid JSON."""
    event = sample_broadcast.event
    result = generate_broadcasts_json(event)

    # Should not raise
    data = json.loads(result)
    assert isinstance(data, dict)


def test_generate_broadcasts_json_has_export_timestamp(sample_event):
    """Test that export includes timestamp."""
    result = generate_broadcasts_json(sample_event)
    data = json.loads(result)

    assert "export_timestamp" in data["summary"]
    assert data["summary"]["export_timestamp"] is not None
