import json
import tempfile
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.models import Broadcast, Event, Registration, utcnow
from src.r2_upload import is_r2_configured, upload_to_r2


def get_template_env() -> Environment:
    template_dir = Path(__file__).parent / "templates"
    return Environment(loader=FileSystemLoader(template_dir), autoescape=True)


def parse_failure_reasons(broadcast: Broadcast) -> dict:
    """Parse failure_reasons JSON field, handling both string and None."""
    if not broadcast.failure_reasons:
        return {}
    if isinstance(broadcast.failure_reasons, str):
        try:
            return json.loads(broadcast.failure_reasons)
        except json.JSONDecodeError:
            return {}
    return {}


def get_broadcast_date(broadcast: Broadcast) -> str:
    """Extract date string from broadcast.sent_at, handling both datetime and string."""
    sent_at = broadcast.sent_at
    if hasattr(sent_at, "strftime"):
        return sent_at.strftime("%Y-%m-%d")
    return str(sent_at)[:10]


def collect_event_data(event: Event) -> dict:
    registrations = list(Registration.select().where(Registration.event == event))

    confirmed_count = sum(1 for r in registrations if r.confirmed and not r.cancelled)
    cancelled_count = sum(1 for r in registrations if r.cancelled)
    pending_count = len(registrations) - confirmed_count - cancelled_count

    broadcasts = list(
        Broadcast.select()
        .where(Broadcast.event == event)
        .order_by(Broadcast.sent_at.desc())
    )

    total_sent = sum(b.sent_count for b in broadcasts)
    total_failed = sum(b.failed_count for b in broadcasts)
    total_messages = total_sent + total_failed
    delivery_rate = round(
        (total_sent / total_messages * 100) if total_messages > 0 else 0, 1
    )

    timeline = build_registration_timeline(registrations)

    # Collect broadcast dates for timeline markers
    broadcast_dates = [get_broadcast_date(b) for b in broadcasts]

    # Parse failure reasons for each broadcast
    broadcasts_with_failures = [
        {
            "broadcast": b,
            "failure_details": parse_failure_reasons(b),
        }
        for b in broadcasts
    ]

    return {
        "event": event,
        "stats": {
            "total_registrations": len(registrations),
            "confirmed_count": confirmed_count,
            "cancelled_count": cancelled_count,
            "pending_count": pending_count,
            "total_broadcasts": len(broadcasts),
            "total_messages_sent": total_sent,
            "total_messages_failed": total_failed,
            "delivery_rate": delivery_rate,
        },
        "broadcasts": broadcasts,
        "broadcasts_with_failures": broadcasts_with_failures,
        "broadcast_dates": broadcast_dates,
        "registration_timeline": timeline,
        "generated_at": utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }


def build_registration_timeline(registrations: list[Registration]) -> dict:
    if not registrations:
        return {"labels": [], "cumulative": []}

    daily_counts: dict[str, int] = defaultdict(int)
    for reg in registrations:
        registered_at = reg.registered_at
        if hasattr(registered_at, "strftime"):
            day = registered_at.strftime("%Y-%m-%d")
        else:
            day = str(registered_at)[:10]
        daily_counts[day] += 1

    sorted_days = sorted(daily_counts.keys())
    cumulative = []
    running_total = 0
    for day in sorted_days:
        running_total += daily_counts[day]
        cumulative.append(running_total)

    return {"labels": sorted_days, "cumulative": cumulative}


def generate_visualization_html(event: Event) -> str:
    data = collect_event_data(event)
    env = get_template_env()
    template = env.get_template("visualization.html.j2")
    return template.render(**data)


def save_visualization_local(html: str, event: Event) -> Path:
    tmp_dir = Path(tempfile.gettempdir())
    filename = f"event_{event.code}_{utcnow().strftime('%Y%m%d_%H%M%S')}.html"
    filepath = tmp_dir / filename
    filepath.write_text(html, encoding="utf-8")
    return filepath


def generate_and_upload_visualization(event: Event, *, local: bool = False) -> tuple[str, bool]:
    """Returns (url_or_path, is_remote)."""
    html = generate_visualization_html(event)

    if local:
        path = save_visualization_local(html, event)
        return str(path), False

    if not is_r2_configured():
        raise RuntimeError("R2 not configured. Use '/visualize local' for local testing.")

    filename = f"event_{event.code}_{utcnow().strftime('%Y%m%d_%H%M%S')}.html"
    url = upload_to_r2(html.encode("utf-8"), filename)
    return url, True
