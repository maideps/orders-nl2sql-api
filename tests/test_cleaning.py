import sqlite3

import pandas as pd

from app.cleaning import COLUMNS, clean_orders, parse_date
from app.generate_data import generate_orders
from app.load_orders import load_orders


def _raw(rows: list[list[str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=COLUMNS)


def test_duplicated_order_is_kept_once():
    row = ["ORD-1", "2025-03-10", "Ana Garcia", "Spain", "Laptop", "950.00", "completed"]

    orders, report = clean_orders(_raw([row, row]))

    assert len(orders) == 1
    assert report.duplicates_removed == 1


def test_dates_in_other_formats_become_iso():
    raw = _raw(
        [
            ["ORD-1", "10/03/2025", "Ana Garcia", "Spain", "Laptop", "950.00", "completed"],
            ["ORD-2", "2025/03/11", "Ana Garcia", "Spain", "Mouse", "19.90", "completed"],
            ["ORD-3", "12-03-2025", "Ana Garcia", "Spain", "Mouse", "19.90", "completed"],
        ]
    )

    orders, report = clean_orders(raw)

    assert orders["order_date"].tolist() == ["2025-03-10", "2025-03-11", "2025-03-12"]
    assert report.dates_reformatted == 3


def test_rows_with_unrecoverable_dates_are_dropped_and_counted():
    raw = _raw(
        [
            ["ORD-1", "2025-02-30", "Ana Garcia", "Spain", "Laptop", "950.00", "completed"],
            ["ORD-2", "not a date", "Ana Garcia", "Spain", "Mouse", "19.90", "completed"],
            ["ORD-3", "", "Ana Garcia", "Spain", "Mouse", "19.90", "completed"],
            ["ORD-4", "2025-03-10", "Ana Garcia", "Spain", "Mouse", "19.90", "completed"],
        ]
    )

    orders, report = clean_orders(raw)

    assert orders["order_id"].tolist() == ["ORD-4"]
    assert report.invalid_dates_dropped == 3


def test_empty_amount_is_kept_as_null():
    raw = _raw([["ORD-1", "2025-03-10", "Ana Garcia", "Spain", "Laptop", "", "completed"]])

    orders, report = clean_orders(raw)

    assert len(orders) == 1
    assert pd.isna(orders.loc[0, "amount"])
    assert report.empty_amounts_kept_as_null == 1


def test_whitespace_is_trimmed_and_status_lowercased():
    raw = _raw(
        [[" ORD-1", "2025-03-10 ", " Ana Garcia ", "Spain ", "Laptop", " 950.00", "Completed "]]
    )

    orders, _ = clean_orders(raw)

    assert orders.loc[0].tolist() == [
        "ORD-1",
        "2025-03-10",
        "Ana Garcia",
        "Spain",
        "Laptop",
        950.00,
        "completed",
    ]


def test_parse_date_reads_slash_dates_as_day_first():
    assert parse_date("03/04/2025").isoformat() == "2025-04-03"


def test_generated_file_is_cleaned_to_the_expected_counts_and_loaded(tmp_path):
    raw = pd.DataFrame(generate_orders(rows=1000, seed=42))
    db_path = tmp_path / "orders.db"

    orders, report = clean_orders(raw)
    load_orders(orders, db_path)

    assert report.rows_read == 1040
    assert report.duplicates_removed == 40
    assert report.dates_reformatted == 50
    assert report.invalid_dates_dropped == 20
    assert report.empty_amounts_kept_as_null == 30
    assert report.rows_clean == 980

    connection = sqlite3.connect(db_path)
    try:
        total, null_amounts, bad_dates = connection.execute(
            "SELECT COUNT(*), SUM(amount IS NULL), SUM(date(order_date) IS NOT order_date) "
            "FROM orders"
        ).fetchone()
    finally:
        connection.close()
    assert (total, null_amounts, bad_dates) == (980, 30, 0)
