import sqlite3

import pandas as pd
import pytest

from app.cleaning import COLUMNS
from app.load_orders import create_views, load_orders


def _order(number: int, day: str, customer: str, country: str, amount, status: str) -> list:
    return [f"ORD-{number}", day, customer, country, "Laptop", amount, status]


@pytest.fixture
def query(tmp_path):
    """Load a small hand-written set of orders and return a function that runs SQL on it."""
    rows = [
        _order(1, "2025-03-05", "Ana Garcia", "Spain", 100.0, "completed"),
        _order(2, "2025-03-20", "Ana Garcia", "Spain", 50.0, "completed"),
        _order(3, "2025-03-21", "Luis Lopez", "Spain", None, "completed"),  # empty amount
        _order(4, "2025-03-22", "Luis Lopez", "Spain", 999.0, "cancelled"),  # not a sale
        _order(5, "2025-04-01", "Ana Garcia", "Spain", 30.0, "completed"),
        _order(6, "2025-03-10", "Marta Perez", "Mexico", 70.0, "completed"),
    ]
    # Twelve more customers so the top-10 limit has something to cut
    rows += [
        _order(100 + i, "2025-06-01", f"Customer {i:02d}", "Chile", float(i), "completed")
        for i in range(1, 13)
    ]
    db_path = tmp_path / "orders.db"
    load_orders(pd.DataFrame(rows, columns=COLUMNS), db_path)
    create_views(db_path)

    connection = sqlite3.connect(db_path)
    yield lambda sql: connection.execute(sql).fetchall()
    connection.close()


def test_sales_are_grouped_by_month_and_country(query):
    rows = query(
        "SELECT month, country, orders, total_sales FROM sales_by_month_country "
        "WHERE country IN ('Spain', 'Mexico') ORDER BY month, country"
    )

    assert rows == [
        ("2025-03", "Mexico", 1, 70.0),
        # 3 completed orders in Spain; the empty amount adds nothing, the cancelled one is out
        ("2025-03", "Spain", 3, 150.0),
        ("2025-04", "Spain", 1, 30.0),
    ]


def test_top_customers_are_the_ten_highest_spenders_in_order(query):
    rows = query("SELECT customer, total_spent FROM top_10_customers")

    assert len(rows) == 10
    assert rows[:2] == [("Ana Garcia", 180.0), ("Marta Perez", 70.0)]
    assert [spent for _, spent in rows] == sorted((spent for _, spent in rows), reverse=True)
    # The cancelled 999.00 order must not put Luis Lopez in the ranking
    assert "Luis Lopez" not in [customer for customer, _ in rows]


def test_views_can_be_recreated_on_an_existing_database(query, tmp_path):
    create_views(tmp_path / "orders.db")

    assert query("SELECT COUNT(*) FROM top_10_customers") == [(10,)]
