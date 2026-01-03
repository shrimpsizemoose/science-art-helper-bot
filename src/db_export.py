from datetime import datetime, UTC

from peewee import Model, SqliteDatabase

from src.models import Broadcast, Event, Registration, User
from src.r2_upload import is_r2_configured, upload_to_r2


def _copy_model_data(source_model: type[Model], export_db: SqliteDatabase) -> int:
    """Copy all data from source model to export database. Returns rows copied."""
    rows = list(source_model.select().dicts())
    if not rows:
        return 0

    # Build field name -> column name mapping for proper SQL column names
    field_to_column = {
        field.name: field.column_name for field in source_model._meta.sorted_fields
    }

    table_name = source_model._meta.table_name
    with export_db.atomic():
        for row in rows:
            processed = {}
            for field_name, value in row.items():
                if hasattr(value, "isoformat"):
                    value = value.isoformat()
                column_name = field_to_column.get(field_name, field_name)
                processed[column_name] = value

            columns = ", ".join(processed.keys())
            placeholders = ", ".join("?" * len(processed))
            export_db.execute_sql(
                f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})",  # noqa: S608
                tuple(processed.values()),
            )

    return len(rows)


def generate_sqlite_export() -> tuple[bytes, dict]:
    """Generate a SQLite export of the entire database in memory.

    Uses sqlite3.Connection.serialize() (Python 3.11+) to avoid file I/O entirely.
    """
    export_db = SqliteDatabase(":memory:")
    export_db.connect()

    source_models = [User, Event, Registration, Broadcast]

    with export_db.bind_ctx(source_models):
        export_db.create_tables(source_models, safe=True)

    total_rows = 0
    for model in source_models:
        rows_copied = _copy_model_data(model, export_db)
        total_rows += rows_copied

    # Serialize in-memory db to bytes - no file I/O needed
    db_bytes = export_db.connection().serialize()
    export_db.close()

    return db_bytes, {"tables": len(source_models), "rows": total_rows}


def generate_and_upload_export() -> tuple[str | bytes, dict, bool]:
    """Generate SQLite export and optionally upload to R2.

    Returns (result, stats, is_url) where result is URL string or file bytes.
    """
    db_bytes, stats = generate_sqlite_export()

    if is_r2_configured():
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"workshop_bot_export_{timestamp}.db"
        url = upload_to_r2(db_bytes, filename, content_type="application/x-sqlite3")
        return url, stats, True

    return db_bytes, stats, False
