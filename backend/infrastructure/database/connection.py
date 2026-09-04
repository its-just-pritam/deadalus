"""SQLite connection factory."""

import sqlite3
from pathlib import Path


def connect(database_path: str | Path) -> sqlite3.Connection:
    """Open a row-oriented SQLite connection with foreign keys enabled."""
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
