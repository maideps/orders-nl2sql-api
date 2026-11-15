"""Tests for POST /ask. The LLM is always replaced by a fake: no network, no API key."""

import sqlite3

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.cleaning import COLUMNS
from app.db import QueryExecutionError, run_query
from app.llm import LLMError, build_system_prompt, extract_sql
from app.load_orders import create_views, load_orders
from app.main import app, get_db_path, get_sql_generator

ORDERS = [
    ["ORD-1", "2025-03-05", "Ana Garcia", "Spain", "Laptop", 950.0, "completed"],
    ["ORD-2", "2025-03-20", "Luis Lopez", "Spain", "Mouse", 50.0, "completed"],
    ["ORD-3", "2025-03-21", "Luis Lopez", "Spain", "Monitor", 210.0, "cancelled"],
    ["ORD-4", "2025-04-02", "Ana Garcia", "Spain", "Mouse", 20.0, "completed"],
    ["ORD-5", "2025-03-11", "Marta Perez", "Mexico", "Laptop", 950.0, "completed"],
]


class FakeSqlGenerator:
    """Stands in for the LLM: returns a fixed answer, or raises a fixed error."""

    def __init__(self, answer: str | Exception):
        self.answer = answer
        self.questions: list[str] = []

    def generate_sql(self, question: str, data: dict) -> str:
        self.questions.append(question)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "orders.db"
    load_orders(pd.DataFrame(ORDERS, columns=COLUMNS), path)
    create_views(path)
    return path


@pytest.fixture
def ask(db_path):
    """Return a function that posts a question with the LLM replaced by `answer`."""

    def _ask(answer: str | Exception, question: str = "¿Cuánto vendimos en España en marzo?"):
        app.dependency_overrides[get_sql_generator] = lambda: FakeSqlGenerator(answer)
        app.dependency_overrides[get_db_path] = lambda: db_path
        return TestClient(app).post("/ask", json={"question": question})

    yield _ask
    app.dependency_overrides.clear()


def test_question_is_answered_with_the_validated_query_result(ask):
    response = ask(
        "SELECT SUM(total_sales) AS total FROM sales_by_month_country "
        "WHERE country = 'Spain' AND month = '2025-03'"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == ["total"]
    assert body["rows"] == [[1000.0]]  # 950 + 50; the cancelled order is not a sale
    assert body["row_count"] == 1
    assert body["sql"].endswith("LIMIT 200")


def test_destructive_sql_from_the_llm_is_rejected_and_never_runs(ask, db_path):
    response = ask("DROP TABLE orders")

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "invalid_query"
    assert body["sql"] == "DROP TABLE orders"
    assert run_query("SELECT COUNT(*) FROM orders", db_path)[1] == [[len(ORDERS)]]


def test_sql_over_a_table_outside_the_allowlist_is_rejected(ask):
    response = ask("SELECT name FROM sqlite_master")

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_query"
    assert "Table not allowed" in response.json()["message"]


def test_llm_answer_that_is_not_sql_is_rejected(ask):
    response = ask("Sure! Here is what I found about your sales.")

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_query"


def test_llm_failure_gives_a_clear_502(ask):
    response = ask(LLMError("The LLM request failed: APITimeoutError."))

    assert response.status_code == 502
    assert response.json() == {
        "error": "llm_error",
        "message": "The LLM request failed: APITimeoutError.",
        "sql": None,
    }


def test_valid_sql_that_sqlite_cannot_run_gives_a_clear_error(ask):
    response = ask("SELECT discount FROM orders")

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "query_execution_failed"
    assert "discount" in body["message"]


def test_missing_database_gives_503(tmp_path):
    app.dependency_overrides[get_sql_generator] = lambda: FakeSqlGenerator("SELECT 1")
    app.dependency_overrides[get_db_path] = lambda: tmp_path / "missing.db"
    try:
        response = TestClient(app).post("/ask", json={"question": "How many orders?"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["error"] == "database_not_found"


def test_empty_question_is_rejected_before_calling_the_llm(ask):
    response = ask("SELECT 1", question="")

    assert response.status_code == 422


def test_connection_is_read_only_even_without_the_validator(db_path):
    """Second barrier: SQLite itself refuses writes on the connection the API uses."""
    with pytest.raises(QueryExecutionError, match="readonly"):
        run_query("DELETE FROM orders", db_path)

    connection = sqlite3.connect(db_path)
    assert connection.execute("SELECT COUNT(*) FROM orders").fetchone() == (len(ORDERS),)
    connection.close()


def test_system_prompt_lists_the_real_values_from_the_database():
    prompt = build_system_prompt(
        {
            "countries": ["Mexico", "Spain"],
            "statuses": ["cancelled", "completed"],
            "products": ["Laptop"],
            "date_range": ["2025-01-01", "2025-12-31"],
        }
    )

    assert "country: Mexico, Spain" in prompt
    assert "from 2025-01-01 to 2025-12-31" in prompt


@pytest.mark.parametrize(
    "text",
    ["SELECT 1", "  SELECT 1\n", "```sql\nSELECT 1\n```", "```\nSELECT 1\n```"],
)
def test_code_fences_around_the_sql_are_removed(text):
    assert extract_sql(text) == "SELECT 1"
