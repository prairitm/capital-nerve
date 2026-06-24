"""Read-only SQLite access to the v3 7-step database."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from config import settings


def connect() -> sqlite3.Connection:
    """Open a read-only connection. Falls back to a normal connection if the
    DB file does not yet exist so the API can still start and return empty
    results / 404s instead of crashing."""
    uri = f"file:{settings.db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    except sqlite3.OperationalError:
        conn = sqlite3.connect(str(settings.db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
