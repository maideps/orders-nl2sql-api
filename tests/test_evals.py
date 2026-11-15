"""Tests for the evaluation tooling itself. They send no request to an LLM.

An evaluation is only worth something if its reference answers are right and its
comparison is fair, so both are tested here.
"""

import pandas as pd
import pytest

from app.cleaning import clean_orders
from app.db import run_query
from app.generate_data import generate_orders
from app.load_orders import create_views, load_orders
from app.validator import validate_query
from evals.run import load_cases, rows_match

CASES = load_cases()
GOLD_CASES = [case for case in CASES if "gold_sql" in case]


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    """The same database the README builds: generated data, cleaned and loaded."""
    path = tmp_path_factory.mktemp("evals") / "orders.db"
    orders, _ = clean_orders(pd.DataFrame(generate_orders(rows=1000, seed=42)))
    load_orders(orders, path)
    create_views(path)
    return path


def test_every_case_is_either_answerable_or_a_refusal_and_ids_are_unique():
    assert len({case["id"] for case in CASES}) == len(CASES)
    for case in CASES:
        assert ("gold_sql" in case) != bool(case.get("expect_refusal")), case["id"]


@pytest.mark.parametrize("case", GOLD_CASES, ids=[case["id"] for case in GOLD_CASES])
def test_reference_queries_are_allowed_and_return_data(case, db_path):
    """A reference query the API itself would reject, or an empty one, proves nothing."""
    _, rows = run_query(validate_query(case["gold_sql"]), db_path)

    assert rows, "the reference query returned no rows"
    assert any(value is not None for value in rows[0]), "the reference result is NULL"


def test_same_values_match_despite_rounding_extra_columns_and_column_order():
    expected = [["Spain", 2440.0], ["Mexico", 100.0]]
    actual = [[100.004, "Mexico", 7], [2440, "Spain", 3]]

    assert rows_match(expected, actual)


def test_a_different_value_or_row_count_does_not_match():
    assert not rows_match([[2440.0]], [[2441.0]])
    assert not rows_match([[1], [2]], [[1]])
    assert not rows_match([[1]], [[1], [2]])


def test_a_value_cannot_be_matched_twice():
    assert not rows_match([[5, 5]], [[5, 9]])
    assert not rows_match([[5], [5]], [[5], [9]])


def test_row_order_matters_only_for_rankings():
    expected = [["Ana"], ["Luis"]]
    actual = [["Luis"], ["Ana"]]

    assert rows_match(expected, actual)
    assert not rows_match(expected, actual, ordered=True)
