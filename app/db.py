"""Read-only access to the orders database.

The validator is the first barrier against unsafe SQL. This module is the second one:
queries run on a connection that SQLite itself opened read-only, and they are stopped
when they take too long.
"""

import sqlite3
import time
from pathlib import Path

QUERY_TIMEOUT_SECONDS = 2.0
# SQLite calls the progress handler every N virtual machine instructions
_PROGRESS_HANDLER_INTERVAL = 10_000


class DatabaseNotFoundError(RuntimeError):
    """The database file does not exist yet: the load script has not been run."""


class QueryExecutionError(RuntimeError):
    """SQLite refused or could not finish the query."""


def _connect_read_only(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise DatabaseNotFoundError(
            f"Database not found at {db_path}. Run `python -m app.load_orders` first."
        )
    return sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)


def run_query(sql: str, db_path: Path) -> tuple[list[str], list[list]]:
    """Run one query and return (column names, rows)."""
    connection = _connect_read_only(db_path)
    deadline = time.monotonic() + QUERY_TIMEOUT_SECONDS
    # Returning a non-zero value makes SQLite abort the running query
    connection.set_progress_handler(
        lambda: int(time.monotonic() > deadline), _PROGRESS_HANDLER_INTERVAL
    )
    try:
        cursor = connection.execute(sql)
        columns = [description[0] for description in cursor.description]
        rows = [list(row) for row in cursor.fetchall()]
    except sqlite3.Error as error:
        raise QueryExecutionError(str(error)) from error
    finally:
        connection.close()
    return columns, rows


def describe_data(db_path: Path) -> dict[str, list[str]]:
    """Return the real values the LLM needs to write correct filters."""
    _, countries = run_query("SELECT DISTINCT country FROM orders ORDER BY country", db_path)
    _, statuses = run_query("SELECT DISTINCT status FROM orders ORDER BY status", db_path)
    _, products = run_query("SELECT DISTINCT product FROM orders ORDER BY product", db_path)
    _, date_range = run_query("SELECT MIN(order_date), MAX(order_date) FROM orders", db_path)
    return {
        "countries": [row[0] for row in countries],
        "statuses": [row[0] for row in statuses],
        "products": [row[0] for row in products],
        "date_range": date_range[0],
    }
