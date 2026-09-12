"""Local persistence for which agenda items have already been processed.

SQLite, per the PRD's demo-scale fallback: it needs no separate service and
the whole store is a single file, which is enough for one city and one
neighborhood profile. Swapping this for DynamoDB later would only mean
reimplementing this module's three functions.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "seen_items.sqlite3"


@contextmanager
def _connection(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS seen_items ("
            "matter_id INTEGER PRIMARY KEY, "
            "first_seen_utc TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        yield conn
        conn.commit()
    finally:
        conn.close()


def is_seen(matter_id: int, db_path: Path = DEFAULT_DB_PATH) -> bool:
    """Whether this agenda item has already been surfaced in a previous run."""
    with _connection(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM seen_items WHERE matter_id = ?", (matter_id,)
        ).fetchone()
        return row is not None


def mark_seen(matter_id: int, db_path: Path = DEFAULT_DB_PATH) -> None:
    """Record an agenda item as processed so re-runs don't re-surface it."""
    with _connection(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen_items (matter_id) VALUES (?)", (matter_id,)
        )


def filter_unseen(items: list[dict], db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """Return only the items from `items` not already marked as seen."""
    with _connection(db_path) as conn:
        seen_ids = {row[0] for row in conn.execute("SELECT matter_id FROM seen_items")}
    return [item for item in items if item["matter_id"] not in seen_ids]
