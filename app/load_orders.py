"""Clean the raw orders CSV, load it into SQLite and create the reporting views.

Usage: python -m app.load_orders [--input data/orders_raw.csv] [--db data/orders.db]

The `orders` table and the views are rebuilt on every run, so running the script twice
gives the same database.
"""

import argparse
import sqlite3
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from app.cleaning import CleaningReport, clean_orders
from app.config import DB_PATH, RAW_CSV_PATH

VIEWS_SQL_PATH = Path(__file__).parent / "sql" / "views.sql"

CREATE_ORDERS_TABLE = """
CREATE TABLE orders (
    order_id   TEXT PRIMARY KEY,
    order_date TEXT NOT NULL,   -- ISO date, YYYY-MM-DD
    customer   TEXT NOT NULL,
    country    TEXT NOT NULL,
    product    TEXT NOT NULL,
    amount     REAL,            -- NULL when the source amount was empty
    status     TEXT NOT NULL
)
"""


def read_raw_csv(path: Path) -> pd.DataFrame:
    """Read every field as text: the cleaning step decides what is valid."""
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def load_orders(orders: pd.DataFrame, db_path: Path) -> None:
    """Replace the `orders` table with the clean rows, in a single transaction."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    rows = orders.astype(object).where(orders.notna(), None).values.tolist()
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            connection.execute("DROP TABLE IF EXISTS orders")
            connection.execute(CREATE_ORDERS_TABLE)
            connection.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    finally:
        connection.close()


def create_views(db_path: Path) -> None:
    """(Re)create the reporting views defined in `app/sql/views.sql`."""
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(VIEWS_SQL_PATH.read_text(encoding="utf-8"))
    finally:
        connection.close()


def run(input_path: Path, db_path: Path) -> CleaningReport:
    orders, report = clean_orders(read_raw_csv(input_path))
    load_orders(orders, db_path)
    create_views(db_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=RAW_CSV_PATH)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()

    report = run(args.input, args.db)
    for name, value in asdict(report).items():
        print(f"{name.replace('_', ' '):<28}{value:>6}")
    print(f"Loaded into {args.db}")


if __name__ == "__main__":
    main()
