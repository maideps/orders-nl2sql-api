import sqlite3

import pandas as pd
import pytest

from app.cleaning import COLUMNS
from app.load_orders import create_views, load_orders
from app.validator import MAX_ROWS, QueryValidationError, validate_query

VALID_QUERIES = [
    "SELECT * FROM orders",
    "SELECT SUM(amount) FROM orders WHERE country = 'Spain' AND status = 'completed'",
    "SELECT total_sales FROM sales_by_month_country WHERE month = '2025-03'",
    "SELECT customer, total_spent FROM top_10_customers ORDER BY total_spent DESC",
    "SELECT strftime('%Y-%m', order_date) AS month, COUNT(*) FROM orders GROUP BY month",
    "WITH spain AS (SELECT * FROM orders WHERE country = 'Spain') SELECT COUNT(*) FROM spain",
    "SELECT customer FROM orders UNION SELECT customer FROM top_10_customers",
    "SELECT * FROM orders WHERE amount > (SELECT AVG(amount) FROM orders)",
    "select * from ORDERS -- trailing comment",
    # A word like "update" or "delete" inside a value is data, not a statement
    "SELECT * FROM orders WHERE product = 'Update' OR status = 'delete'",
]

INVALID_QUERIES = [
    # Not read-only
    ("INSERT INTO orders SELECT * FROM orders", "Only SELECT"),
    ("UPDATE orders SET amount = 0", "Only SELECT"),
    ("DELETE FROM orders", "Only SELECT"),
    ("DROP TABLE orders", "Only SELECT"),
    ("CREATE TABLE copy AS SELECT * FROM orders", "Only SELECT"),
    ("PRAGMA table_info(orders)", "Only SELECT"),
    ("ATTACH DATABASE 'other.db' AS other", "Only SELECT"),
    ("VACUUM", "Only SELECT"),
    ("SELECT * INTO backup FROM orders", "read-only"),
    # More than one statement
    ("SELECT * FROM orders; DROP TABLE orders", "one SQL statement"),
    ("SELECT 1; SELECT 2", "one SQL statement"),
    # Tables outside the allowlist
    ("SELECT * FROM sqlite_master", "Table not allowed"),
    ("SELECT * FROM customers", "Table not allowed"),
    ("SELECT * FROM orders UNION SELECT name, 1, 1, 1, 1, 1, 1 FROM sqlite_master", "not allowed"),
    ("SELECT * FROM orders WHERE amount > (SELECT COUNT(*) FROM sqlite_schema)", "not allowed"),
    ("WITH sqlite_master AS (SELECT 1) SELECT * FROM sqlite_master", "Table not allowed"),
    ("SELECT * FROM main.orders", "Schema-qualified"),
    ("SELECT * FROM pragma_table_info('orders')", "not allowed"),
    # Dangerous functions
    ("SELECT load_extension('evil')", "Function not allowed"),
    ("SELECT readfile('/etc/passwd')", "Function not allowed"),
    # Not SQL at all
    ("", "empty"),
    ("   ", "empty"),
    ("I cannot answer that question", "not valid SQL"),
    ("SELECT * FROM orders WHERE", "not valid SQL"),
]


@pytest.mark.parametrize("sql", VALID_QUERIES)
def test_read_only_queries_over_allowed_tables_are_accepted(sql):
    assert validate_query(sql)


@pytest.mark.parametrize(("sql", "reason"), INVALID_QUERIES)
def test_unsafe_or_malformed_queries_are_rejected_with_a_reason(sql, reason):
    with pytest.raises(QueryValidationError, match=reason):
        validate_query(sql)


def test_a_limit_is_added_when_the_query_has_none():
    assert validate_query("SELECT * FROM orders").endswith(f"LIMIT {MAX_ROWS}")


def test_a_limit_above_the_maximum_is_lowered():
    assert validate_query("SELECT * FROM orders LIMIT 100000").endswith(f"LIMIT {MAX_ROWS}")


def test_a_limit_within_the_maximum_is_kept():
    assert validate_query("SELECT * FROM orders LIMIT 5").endswith("LIMIT 5")


@pytest.mark.parametrize("sql", VALID_QUERIES)
def test_validated_queries_still_run_on_sqlite(sql, tmp_path):
    """The validator rewrites the SQL (to add LIMIT); the result must stay executable."""
    db_path = tmp_path / "orders.db"
    row = ["ORD-1", "2025-03-10", "Ana Garcia", "Spain", "Laptop", 950.0, "completed"]
    load_orders(pd.DataFrame([row], columns=COLUMNS), db_path)
    create_views(db_path)

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(validate_query(sql)).fetchall()
    finally:
        connection.close()
