# orders-nl2sql-api

A Python project built on orders data: it cleans a CSV with errors, loads it into SQLite,
defines SQL views and exposes a FastAPI endpoint that answers natural-language questions
by turning them into validated SQL.

> Work in progress. This README is completed at the end with how to run it, the
> decisions taken, what I would do with more time and how AI was used.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # on Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

## 1. Generate the raw data

```bash
python -m app.generate_data
```

Writes `data/orders_raw.csv`: 1,000 distinct orders plus 40 duplicated rows, with dates
in mixed formats, dates that do not exist and empty amounts. The output is reproducible
(`--seed`, default 42).

## 2. Clean the data and load it into SQLite

```bash
python -m app.load_orders
```

Reads `data/orders_raw.csv`, applies the cleaning rules and rebuilds the `orders` table
in `data/orders.db`. It prints what happened to the rows:

```
rows read                     1040
duplicates removed              40
dates reformatted               50
invalid dates dropped           20
empty amounts kept as null      30
rows clean                     980
```

The same command creates two views, defined in [`app/sql/views.sql`](app/sql/views.sql):

| View | Columns | Meaning |
|------|---------|---------|
| `sales_by_month_country` | `month`, `country`, `orders`, `total_sales` | Completed orders per month (`YYYY-MM`) and country |
| `top_10_customers` | `customer`, `country`, `orders`, `total_spent` | The ten customers who spent the most |

Only orders with status `completed` count as sales.

## Verification

```bash
python check.py
```

Runs the style check (ruff) and the tests (pytest). It must pass before every commit.
