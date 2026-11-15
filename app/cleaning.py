"""Cleaning rules for the raw orders data.

`clean_orders` is a pure function: it takes the raw rows as a DataFrame of strings and
returns the clean DataFrame plus a report with what happened to every row, so nothing
is dropped silently.
"""

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

COLUMNS = ["order_id", "order_date", "customer", "country", "product", "amount", "status"]

# Accepted date formats, tried in order. Dates written with slashes or dashes that do
# not start with the year are read as day first (19/11/2025 is 19 November).
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"]


@dataclass
class CleaningReport:
    rows_read: int
    duplicates_removed: int
    dates_reformatted: int
    invalid_dates_dropped: int
    empty_amounts_kept_as_null: int
    rows_clean: int


def parse_date(value: str) -> date | None:
    """Return the date for any accepted format, or None when it cannot be recovered."""
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    return None


def clean_orders(raw: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    """Apply the cleaning rules and return (clean orders, report).

    Rules, in order:
    1. Trim surrounding whitespace in every field and lowercase `status`.
    2. Keep one row per `order_id` (the first one seen).
    3. Rewrite every date as ISO `YYYY-MM-DD`; drop rows whose date cannot be parsed.
    4. Convert `amount` to a number; an empty amount stays as NULL and the row is kept.
    """
    orders = raw[COLUMNS].apply(lambda column: column.str.strip())
    orders["status"] = orders["status"].str.lower()
    rows_read = len(orders)

    orders = orders.drop_duplicates(subset="order_id", keep="first")
    duplicates_removed = rows_read - len(orders)

    parsed_dates = orders["order_date"].map(parse_date)
    is_valid_date = parsed_dates.notna()
    iso_dates = parsed_dates[is_valid_date].map(date.isoformat)
    dates_reformatted = int((iso_dates != orders.loc[is_valid_date, "order_date"]).sum())
    invalid_dates_dropped = int((~is_valid_date).sum())

    orders = orders[is_valid_date].copy()
    orders["order_date"] = iso_dates

    orders["amount"] = pd.to_numeric(orders["amount"].replace("", None), errors="coerce")
    empty_amounts = int(orders["amount"].isna().sum())

    report = CleaningReport(
        rows_read=rows_read,
        duplicates_removed=duplicates_removed,
        dates_reformatted=dates_reformatted,
        invalid_dates_dropped=invalid_dates_dropped,
        empty_amounts_kept_as_null=empty_amounts,
        rows_clean=len(orders),
    )
    return orders.reset_index(drop=True), report
