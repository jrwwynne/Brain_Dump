"""
db.py — SQLite database initialisation and task CRUD operations

The database file lives at data/tasks.db relative to this module.
The tasks table is created automatically on first run.

Schema
------
id              INTEGER PRIMARY KEY AUTOINCREMENT
task_text       TEXT NOT NULL
status          TEXT NOT NULL DEFAULT 'pending'   -- 'pending' | 'completed'
created_at      TEXT NOT NULL                     -- ISO-8601 UTC timestamp
completed_at    TEXT                              -- ISO-8601 UTC timestamp, nullable
source_transcript TEXT                            -- raw transcript that generated this task
updated_at      TEXT NOT NULL                     -- ISO-8601 UTC timestamp
"""

import sqlite3
import os
from datetime import datetime, timezone

# Resolve the path relative to this file so the app works regardless of
# the working directory from which it is launched.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_BASE_DIR, "data", "tasks.db")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    task_text         TEXT    NOT NULL,
    status            TEXT    NOT NULL DEFAULT 'pending',
    created_at        TEXT    NOT NULL,
    completed_at      TEXT,
    source_transcript TEXT,
    updated_at        TEXT    NOT NULL
);
"""


def _now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect() -> sqlite3.Connection:
    """Open a connection with row_factory so rows behave like dicts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the database and tables if they do not already exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _connect() as conn:
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()
    print(f"[db] Database ready at {DB_PATH}")


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------

def insert_task(task_text: str, source_transcript: str = "") -> int:
    """Insert a new pending task and return its id."""
    now = _now()
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks (task_text, status, created_at, source_transcript, updated_at)
            VALUES (?, 'pending', ?, ?, ?)
            """,
            (task_text, now, source_transcript, now),
        )
        conn.commit()
        return cursor.lastrowid


def get_all_tasks() -> list[dict]:
    """Return all tasks ordered by created_at descending."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_pending_tasks() -> list[dict]:
    """Return all pending tasks ordered by created_at descending."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_completed_tasks() -> list[dict]:
    """Return all completed tasks ordered by completed_at descending."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status = 'completed' ORDER BY completed_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def mark_complete(task_id: int) -> bool:
    """Mark a task as completed. Returns True if a row was updated."""
    now = _now()
    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE tasks
            SET status = 'completed', completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, task_id),
        )
        conn.commit()
    return cursor.rowcount > 0


def mark_pending(task_id: int) -> bool:
    """Revert a completed task back to pending. Returns True if updated."""
    now = _now()
    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE tasks
            SET status = 'pending', completed_at = NULL, updated_at = ?
            WHERE id = ?
            """,
            (now, task_id),
        )
        conn.commit()
    return cursor.rowcount > 0


def delete_task(task_id: int) -> bool:
    """Delete a single task by id. Returns True if a row was deleted."""
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
    return cursor.rowcount > 0


def clear_completed() -> int:
    """Delete all completed tasks. Returns the number of rows deleted."""
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM tasks WHERE status = 'completed'")
        conn.commit()
    return cursor.rowcount
