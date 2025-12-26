import json

from src.models import Broadcast, Event, utcnow


def generate_broadcasts_json(event: Event) -> str:
    """Generate JSON export of broadcast history for an event.

    The format is designed to be flexible for various visualization tools
    like D3.js, Chart.js, or Observable.
    """
    broadcasts = (
        Broadcast.select()
        .where(Broadcast.event == event)
        .order_by(Broadcast.sent_at.asc())
    )

    broadcasts_data = []
    total_sent = 0
    total_failed = 0

    for bc in broadcasts:
        sent_at = bc.sent_at
        if hasattr(sent_at, "isoformat"):
            sent_at_str = sent_at.isoformat()
        else:
            sent_at_str = str(sent_at)

        broadcasts_data.append({
            "id": bc.id,
            "message_text": bc.message_text,
            "target_audience": bc.target_audience,
            "include_buttons": bc.include_buttons,
            "sent_count": bc.sent_count,
            "failed_count": bc.failed_count,
            "sent_at": sent_at_str,
        })
        total_sent += bc.sent_count
        total_failed += bc.failed_count

    # Format event dates
    created_at = event.created_at
    if hasattr(created_at, "isoformat"):
        created_at_str = created_at.isoformat()
    else:
        created_at_str = str(created_at)

    archived_at = event.archived_at
    if archived_at:
        if hasattr(archived_at, "isoformat"):
            archived_at_str = archived_at.isoformat()
        else:
            archived_at_str = str(archived_at)
    else:
        archived_at_str = None

    export_data = {
        "event": {
            "id": event.id,
            "title": event.title,
            "code": event.code,
            "datetime_text": event.datetime_text,
            "is_active": event.is_active,
            "created_at": created_at_str,
            "archived_at": archived_at_str,
        },
        "broadcasts": broadcasts_data,
        "summary": {
            "total_broadcasts": len(broadcasts_data),
            "total_recipients_reached": total_sent,
            "total_failed_deliveries": total_failed,
            "export_timestamp": utcnow().isoformat(),
        },
    }

    return json.dumps(export_data, indent=2, ensure_ascii=False)
