from collections import Counter
from datetime import date

from app.generate_data import COLUMNS, generate_orders, write_csv


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def test_generates_at_least_1000_distinct_orders_with_all_columns():
    rows = generate_orders(rows=1000, seed=42)

    assert len({row["order_id"] for row in rows}) == 1000
    assert all(list(row) == COLUMNS for row in rows)


def test_contains_the_three_deliberate_errors():
    rows = generate_orders(rows=1000, seed=42)

    id_counts = Counter(row["order_id"] for row in rows)
    duplicated_ids = [order_id for order_id, count in id_counts.items() if count > 1]
    non_iso_dates = [row for row in rows if not _is_iso_date(row["order_date"])]
    empty_amounts = [row for row in rows if row["amount"] == ""]

    assert len(duplicated_ids) == 40
    assert len(non_iso_dates) >= 50  # reformatted dates plus most of the invalid ones
    assert len(empty_amounts) >= 30  # duplicates can repeat a row with an empty amount


def test_same_seed_gives_the_same_file(tmp_path):
    first, second = tmp_path / "first.csv", tmp_path / "second.csv"

    write_csv(generate_orders(rows=200, seed=7), first)
    write_csv(generate_orders(rows=200, seed=7), second)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
