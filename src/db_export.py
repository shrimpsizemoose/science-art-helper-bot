import os
import tempfile
from datetime import datetime, UTC
from pathlib import Path

from peewee import Model, SqliteDatabase

from src.models import Broadcast, Event, Registration, User
from src.r2_upload import is_r2_configured, upload_to_r2


def _get_temp_dir() -> Path:
    """Find a writable temp directory, trying multiple fallback locations."""
    candidates = [
        tempfile.gettempdir(),
        "/tmp",
        "/app/tmp",
        "/app",
        os.getcwd(),
    ]
    for candidate in candidates:
        path = Path(candidate)
        try:
            path.mkdir(parents=True, exist_ok=True)
            # Test if writable
            test_file = path / ".write_test"
            test_file.touch()
            test_file.unlink()
            return path
        except (OSError, PermissionError):
            continue
    raise OSError("No usable temporary directory found")


def _copy_model_data(source_model: type[Model], export_db: SqliteDatabase) -> int:
    """Copy all data from source model to export database. Returns rows copied."""
    rows = list(source_model.select().dicts())
    if not rows:
        return 0

    # Build field name -> column name mapping for proper SQL column names
    field_to_column = {
        field.name: field.column_name
        for field in source_model._meta.sorted_fields
    }

    table_name = source_model._meta.table_name
    with export_db.atomic():
        for row in rows:
            # Convert datetime objects and map field names to column names
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


def generate_sqlite_export() -> tuple[Path, dict]:
    """Generate a SQLite export of the entire database.

    Returns (path_to_sqlite_file, stats_dict with 'tables' and 'rows').
    """
    temp_dir = _get_temp_dir()
    export_path = temp_dir / f"workshop_bot_export_{os.getpid()}.db"

    export_db = SqliteDatabase(str(export_path))
    export_db.connect()

    source_models = [User, Event, Registration, Broadcast]

    # Temporarily bind models to export db to create tables with correct schema
    with export_db.bind_ctx(source_models):
        export_db.create_tables(source_models, safe=True)

    total_rows = 0
    for model in source_models:
        rows_copied = _copy_model_data(model, export_db)
        total_rows += rows_copied

    export_db.close()

    return export_path, {"tables": len(source_models), "rows": total_rows}


def generate_and_upload_export() -> tuple[str | bytes, dict, bool]:
    """Generate SQLite export and optionally upload to R2.

    Returns:
        (result, stats, is_url) where:
        - result is either a URL string (if R2 configured) or file bytes
        - stats is dict with 'tables' and 'rows'
        - is_url is True if result is a URL, False if bytes
    """
    export_path, stats = generate_sqlite_export()

    try:
        file_bytes = export_path.read_bytes()

        if is_r2_configured():
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            filename = f"workshop_bot_export_{timestamp}.db"
            url = upload_to_r2(file_bytes, filename, content_type="application/x-sqlite3")
            return url, stats, True
        else:
            return file_bytes, stats, False
    finally:
        export_path.unlink(missing_ok=True)
