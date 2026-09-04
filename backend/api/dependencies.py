"""FastAPI dependencies shared by controllers."""

from collections.abc import Generator
import os
from pathlib import Path
import sqlite3

from backend.infrastructure.database.connection import connect


DATABASE_PATH = Path(
    os.environ.get(
        "CREW_OPERATIONS_DB",
        str(Path(__file__).resolve().parents[2] / "crew_operations.db"),
    )
)


def get_connection() -> Generator[sqlite3.Connection, None, None]:
    connection = connect(DATABASE_PATH)
    try:
        yield connection
    finally:
        connection.close()
