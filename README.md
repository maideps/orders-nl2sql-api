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

## Verification

```bash
python check.py
```

Runs the style check (ruff) and the tests (pytest). It must pass before every commit.
