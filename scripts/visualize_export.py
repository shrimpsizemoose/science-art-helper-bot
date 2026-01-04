#!/usr/bin/env python3
"""Generate visualization HTML from an exported SQLite database.

Usage:
    python scripts/visualize_export.py path/to/exported.db [--event CODE] [--output DIR]
"""

import argparse
import sys
from pathlib import Path

from peewee import SqliteDatabase

from src.models import Event, db
from src.visualization import generate_visualization_html


def main():
    parser = argparse.ArgumentParser(
        description="Generate visualization HTML from exported database"
    )
    parser.add_argument("db_path", help="Path to exported SQLite database")
    parser.add_argument("--event", "-e", help="Event code to visualize (default: all)")
    parser.add_argument(
        "--output", "-o", default=".", help="Output directory (default: current)"
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Error: Database file not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Point the db proxy to the exported SQLite file
    db.initialize(SqliteDatabase(str(db_path)))
    db.connect()

    try:
        if args.event:
            events = list(Event.select().where(Event.code == args.event))
            if not events:
                print(f"Error: Event '{args.event}' not found", file=sys.stderr)
                sys.exit(1)
        else:
            events = list(Event.select())

        if not events:
            print("No events found in database", file=sys.stderr)
            sys.exit(1)

        print(f"Found {len(events)} event(s)")

        for event in events:
            print(f"  {event.title} ({event.code})")
            html = generate_visualization_html(event)
            output_path = output_dir / f"event_{event.code}.html"
            output_path.write_text(html, encoding="utf-8")
            print(f"    -> {output_path}")

    finally:
        db.close()

    print("Done!")


if __name__ == "__main__":
    main()
