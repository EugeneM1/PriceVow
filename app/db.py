"""SQLite persistence - Python's built-in database, no server needed.

One file on disk (data/pricevow.db) holds every quote we ever issued
and every invoiced cost a contractor reported back. Those two tables
together are the calibration dataset - the moat.

Set the PRICEVOW_DB environment variable to use a different file
(tests point it at a temporary path so they never touch real data).
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "pricevow.db"


def _db_path() -> Path:
    return Path(os.environ.get("PRICEVOW_DB", DEFAULT_DB))


def connect() -> sqlite3.Connection:
    """Open the database, creating the tables on first use."""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            zip_code TEXT,
            trade TEXT NOT NULL DEFAULT 'fence',
            scope_json TEXT NOT NULL,        -- the full Scope, for audits
            scope_source TEXT,               -- form | vision | form+vision
            bindable_prob REAL NOT NULL,
            risk_tier TEXT NOT NULL,
            expected_cost REAL NOT NULL,
            low REAL NOT NULL,
            high REAL NOT NULL,
            ceiling REAL,                    -- NULL when we did not bind
            bound INTEGER NOT NULL,          -- 1 = we promised the ceiling
            rate_card_version TEXT NOT NULL,
            booked INTEGER NOT NULL DEFAULT 0 -- homeowner accepted the ceiling
        );
        CREATE TABLE IF NOT EXISTS invoices (
            job_id TEXT PRIMARY KEY REFERENCES jobs(id),
            invoiced_cost REAL NOT NULL,
            recorded_at TEXT NOT NULL
        );
        """
    )
    # Lenient migration for databases created before the booked column.
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN booked INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # column already exists
    return conn


def new_job_id() -> str:
    """Short, human-readable id like PV-3F2A9C."""
    return "PV-" + uuid.uuid4().hex[:6].upper()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def scope_to_json(scope) -> str:
    return json.dumps(scope.__dict__)
