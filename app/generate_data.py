"""Generate a raw orders CSV that contains deliberate data-quality errors.

Usage: python -m app.generate_data [--rows 1000] [--seed 42] [--output data/orders_raw.csv]

The file has `rows` distinct orders plus extra duplicated rows. Some rows carry a
date in a different format, a date that does not exist, or an empty amount. The seed
makes the output reproducible, so the CSV itself is not committed.
"""

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

COLUMNS = ["order_id", "order_date", "customer", "country", "product", "amount", "status"]

COUNTRIES = ["Spain", "Mexico", "Argentina", "Colombia", "Chile", "Portugal", "France", "Germany"]

# Product name -> unit price in USD
PRODUCTS = {
    "Laptop": 950.00,
    "Monitor": 210.00,
    "Keyboard": 45.50,
    "Mouse": 19.90,
    "Headphones": 79.00,
    "Webcam": 59.90,
    "Docking Station": 129.00,
    "External SSD": 110.00,
    "Office Chair": 240.00,
    "Standing Desk": 420.00,
}

STATUSES = ["completed", "pending", "cancelled", "refunded"]
STATUS_WEIGHTS = [70, 12, 10, 8]

FIRST_NAMES = [
    "Ana",
    "Luis",
    "Marta",
    "Carlos",
    "Elena",
    "Diego",
    "Laura",
    "Pablo",
    "Sofia",
    "Javier",
]
LAST_NAMES = ["Garcia", "Lopez", "Martinez", "Perez", "Sanchez", "Romero", "Torres", "Vargas"]

FIRST_DAY = date(2025, 1, 1)
DAYS_IN_RANGE = 365

# Share of the distinct orders that receives each kind of error
DUPLICATE_RATE = 0.04
REFORMATTED_DATE_RATE = 0.05
INVALID_DATE_RATE = 0.02
EMPTY_AMOUNT_RATE = 0.03

# Dates that no parser can recover: the cleaning step must drop these rows
INVALID_DATES = ["2025-02-30", "2025-13-01", "31/04/2025", "not a date", ""]


def _build_customers(rng: random.Random) -> list[tuple[str, str]]:
    """Return (name, country) pairs; each customer always orders from one country."""
    names = [f"{first} {last}" for first in FIRST_NAMES for last in LAST_NAMES]
    return [(name, rng.choice(COUNTRIES)) for name in names]


def _reformat_date(day: date, rng: random.Random) -> str:
    """Write a valid date in a non-ISO format that the cleaning step can still parse."""
    return rng.choice(
        [day.strftime("%d/%m/%Y"), day.strftime("%Y/%m/%d"), day.strftime("%d-%m-%Y")]
    )


def generate_orders(rows: int = 1000, seed: int = 42) -> list[dict[str, str]]:
    """Return the raw rows: `rows` distinct orders plus duplicates, in random order."""
    rng = random.Random(seed)
    customers = _build_customers(rng)
    # A few customers buy much more often, so the "top customers" view is meaningful
    customer_weights = [rng.choice([1, 1, 1, 2, 3, 8]) for _ in customers]
    products = list(PRODUCTS)

    orders = []
    for number in range(1, rows + 1):
        customer, country = rng.choices(customers, weights=customer_weights)[0]
        product = rng.choice(products)
        quantity = rng.randint(1, 5)
        day = FIRST_DAY + timedelta(days=rng.randrange(DAYS_IN_RANGE))
        orders.append(
            {
                "order_id": f"ORD-{number:05d}",
                "order_date": day.isoformat(),
                "customer": customer,
                "country": country,
                "product": product,
                "amount": f"{PRODUCTS[product] * quantity:.2f}",
                "status": rng.choices(STATUSES, weights=STATUS_WEIGHTS)[0],
            }
        )

    # Each error type goes to a separate set of rows, so the counts are exact
    shuffled = rng.sample(orders, k=len(orders))
    n_reformatted = int(rows * REFORMATTED_DATE_RATE)
    n_invalid = int(rows * INVALID_DATE_RATE)
    n_empty = int(rows * EMPTY_AMOUNT_RATE)

    for order in shuffled[:n_reformatted]:
        order["order_date"] = _reformat_date(date.fromisoformat(order["order_date"]), rng)
    for order in shuffled[n_reformatted : n_reformatted + n_invalid]:
        order["order_date"] = rng.choice(INVALID_DATES)
    for order in shuffled[n_reformatted + n_invalid : n_reformatted + n_invalid + n_empty]:
        order["amount"] = ""

    duplicates = [dict(order) for order in rng.sample(orders, k=int(rows * DUPLICATE_RATE))]
    raw_rows = orders + duplicates
    rng.shuffle(raw_rows)
    return raw_rows


def write_csv(rows: list[dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=int, default=1000, help="number of distinct orders")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("data/orders_raw.csv"))
    args = parser.parse_args()

    rows = generate_orders(rows=args.rows, seed=args.seed)
    write_csv(rows, args.output)
    print(f"Wrote {len(rows)} rows ({args.rows} distinct orders) to {args.output}")


if __name__ == "__main__":
    main()
