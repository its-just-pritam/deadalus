import json
import re
import sqlite3
from pathlib import Path
from typing import Any


DATA_DIR = Path("/data")
DATABASE_PATH = Path("/var/lib/sqlite/crew_operations.db")
CHAT_HISTORY_TABLE = "chat_history"
TOOL_CALLS_TABLE = "tool_calls"


def table_name(path: Path) -> str:
    return path.stem.lower().replace("-", "_")


def records_from_json(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        list_values = [value for value in payload.values() if isinstance(value, list)]
        if len(list_values) == 1 and len(payload) == 1:
            return list_values[0]

    return [payload]


def sql_name(value: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return name or "value"


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def scalar_type(value: Any) -> str:
    if isinstance(value, bool):
        return "INTEGER"
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "REAL"
    return "TEXT"


def collect_tables(
    table: str,
    records: list[Any],
    parent: tuple[str, Any] | None,
    tables: dict[str, dict[str, Any]],
) -> None:
    table = sql_name(table)
    table_info = tables.setdefault(
        table,
        {"columns": {}, "rows": [], "parent": parent, "unique_columns": set()},
    )

    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            record = {"value": record}

        row: dict[str, Any] = {}
        if parent:
            row["parent_id"] = parent[1]
            table_info["columns"]["parent_id"] = "INTEGER"

        row_id = len(table_info["rows"]) + 1
        row["id"] = row_id
        table_info["columns"]["id"] = "INTEGER"

        for original_field, value in record.items():
            field = sql_name(original_field)
            if field == "expected_answer":
                row[field] = json.dumps(value, separators=(",", ":"))
                table_info["columns"][field] = "TEXT"
            elif isinstance(value, dict):
                collect_tables(f"{table}_{field}", [value], (table, row_id), tables)
            elif isinstance(value, list):
                collect_tables(f"{table}_{field}", value, (table, row_id), tables)
            else:
                row[field] = value
                table_info["columns"][field] = scalar_type(value)

        table_info["rows"].append(row)


def finalize_unique_columns(tables: dict[str, dict[str, Any]]) -> None:
    for info in tables.values():
        for column in info["columns"]:
            values = [row.get(column) for row in info["rows"]]
            if column != "id" and values and None not in values and len(values) == len(set(values)):
                info["unique_columns"].add(column)


def foreign_key_target(
    table: str, column: str, tables: dict[str, dict[str, Any]]
) -> tuple[str, str] | None:
    if column == "parent_id":
        return None
    stem = column.removesuffix("_id")
    canonical_names = {
        "crew": "crew",
        "flight": "flights",
        "pairing": "rosters_pairings",
        "question": "questions",
        "scenario": "scenarios",
        "rule": "rules_rules",
    }
    canonical_table = canonical_names.get(stem)
    if (
        canonical_table in tables
        and canonical_table != table
        and column in tables[canonical_table]["unique_columns"]
    ):
        return canonical_table, column

    return None


def create_tables(connection: sqlite3.Connection, tables: dict[str, dict[str, Any]]) -> None:
    for table in tables:
        connection.execute(f"DROP TABLE IF EXISTS {quote_identifier(table)}")

    for table, info in tables.items():
        definitions = []
        for column, data_type in info["columns"].items():
            definition = f"{quote_identifier(column)} {data_type}"
            if column == "id":
                definition += " PRIMARY KEY"
            elif column in info["unique_columns"]:
                definition += " UNIQUE"
            definitions.append(definition)

        if info["parent"]:
            parent_table, _ = info["parent"]
            definitions.append(
                f"FOREIGN KEY ({quote_identifier('parent_id')}) REFERENCES "
                f"{quote_identifier(parent_table)} ({quote_identifier('id')})"
            )
        for column in info["columns"]:
            target = foreign_key_target(table, column, tables)
            if target:
                target_table, target_column = target
                definitions.append(
                    f"FOREIGN KEY ({quote_identifier(column)}) REFERENCES "
                    f"{quote_identifier(target_table)} ({quote_identifier(target_column)})"
                )

        connection.execute(
            f"CREATE TABLE {quote_identifier(table)} ({', '.join(definitions)})"
        )

def insert_tables(connection: sqlite3.Connection, tables: dict[str, dict[str, Any]]) -> None:
    for table, info in tables.items():
        columns = list(info["columns"])
        placeholders = ", ".join("?" for _ in columns)
        column_list = ", ".join(quote_identifier(column) for column in columns)
        for row in info["rows"]:
            connection.execute(
                f"INSERT INTO {quote_identifier(table)} ({column_list}) VALUES ({placeholders})",
                [row.get(column) for column in columns],
            )


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def create_chat_history_table(connection: sqlite3.Connection) -> None:
    if table_exists(connection, CHAT_HISTORY_TABLE):
        return
    connection.execute(
        """
        CREATE TABLE chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            source_question TEXT,
            created_at TEXT NOT NULL,
            response_time_ms INTEGER
        )
        """
    )


def create_tool_calls_table(connection: sqlite3.Connection) -> None:
    if table_exists(connection, TOOL_CALLS_TABLE):
        return
    connection.execute(
        """
        CREATE TABLE tool_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            tool_name TEXT NOT NULL,
            method TEXT NOT NULL,
            request_url TEXT NOT NULL,
            curl_command TEXT NOT NULL,
            status_code INTEGER,
            duration_ms REAL,
            success INTEGER NOT NULL,
            error_message TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (message_id) REFERENCES chat_history (id)
        )
        """
    )


def main() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    json_files = sorted(DATA_DIR.glob("*.json"))
    if not json_files:
        raise RuntimeError(f"No JSON files found in {DATA_DIR}")

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        existing_tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        for (table,) in existing_tables:
            if table in {CHAT_HISTORY_TABLE, TOOL_CALLS_TABLE, "sqlite_sequence"}:
                continue
            connection.execute(f"DROP TABLE IF EXISTS {quote_identifier(table)}")

        tables: dict[str, dict[str, Any]] = {}
        for path in json_files:
            payload = json.loads(path.read_text(encoding="utf-8"))
            records = records_from_json(payload)
            collect_tables(table_name(path), records, None, tables)
            print(
                f"Read {len(records)} record(s) from {path.name}"
            )

        finalize_unique_columns(tables)
        create_tables(connection, tables)
        insert_tables(connection, tables)
        create_chat_history_table(connection)
        create_tool_calls_table(connection)
        connection.execute("PRAGMA foreign_keys = ON")
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Foreign-key validation failed: {violations[:5]}")

    print(f"SQLite database created at {DATABASE_PATH} with {len(tables)} normalized table(s)")


if __name__ == "__main__":
    main()