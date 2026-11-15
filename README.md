# orders-nl2sql-api

[![CI](https://github.com/maideps/orders-nl2sql-api/actions/workflows/ci.yml/badge.svg)](https://github.com/maideps/orders-nl2sql-api/actions/workflows/ci.yml)

A small Python project built on orders data. It cleans a CSV that contains deliberate
errors, loads it into SQLite, defines two reporting views and exposes a FastAPI endpoint
that answers questions in natural language: an LLM writes the SQL, the SQL is validated,
and only then is it run.

```
question ──> LLM writes SQL ──> validator ──> read-only SQLite ──> rows + the SQL that ran
                  │                 │                │
              502 llm_error    422 invalid_query   422 query_execution_failed
              422 question_not_answerable
```

Contents: [How to run it](#how-to-run-it) · [Tests](#tests) · [Evaluation](#evaluation) ·
[Decisions](#decisions) · [With more time](#what-i-would-do-with-more-time) ·
[How I used AI](#how-i-used-ai)

## How to run it

Requires Python 3.11 or newer.

### Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # on Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

### 1. Generate the raw data

```bash
python -m app.generate_data
```

Writes `data/orders_raw.csv`: 1,000 distinct orders plus 40 duplicated rows, with dates
in mixed formats, dates that do not exist and empty amounts. The output is reproducible
(`--seed`, default 42), so the CSV is not committed.

### 2. Clean the data and load it into SQLite

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

### 3. Ask questions through the API

Copy `.env.example` to `.env` and set `LLM_API_KEY` to an OpenAI key. Any provider with
an OpenAI-compatible API works: for DeepSeek, also set `LLM_BASE_URL` and `LLM_MODEL` as
shown in `.env.example`. The key is never committed: `.env` is in `.gitignore`.

```bash
uvicorn app.main:app --reload
```

Ask a question, from the interactive docs at http://127.0.0.1:8000/docs or with curl:

```bash
curl -X POST http://127.0.0.1:8000/ask -H "Content-Type: application/json" -d "{\"question\": \"How much did we sell in Spain in March?\"}"
```

A successful answer returns the SQL that ran and its result:

```json
{
  "question": "How much did we sell in Spain in March?",
  "sql": "SELECT total_sales FROM sales_by_month_country WHERE month = '2025-03' AND country = 'Spain' LIMIT 200",
  "columns": ["total_sales"],
  "rows": [[2440.0]],
  "row_count": 1
}
```

This is the real answer from `gpt-5-mini` on the generated data. The exact SQL can vary
between runs, since it is written by the LLM. Questions can be asked in other languages:
"¿Cuánto vendimos en España en marzo?" gives the same result.

When something fails, the response says which step failed:

| Status | `error` | Meaning |
|--------|---------|---------|
| 422 | `invalid_query` | The LLM's SQL is not a single read-only query over the allowed tables. It was not run. |
| 422 | `query_execution_failed` | The SQL was valid but SQLite could not run it. |
| 422 | `question_not_answerable` | The LLM replied that the orders data cannot answer the question (off-topic, or a request to change data). |
| 502 | `llm_error` | The LLM call failed, was declined, was cut off or came back empty. |
| 503 | `database_not_found` | Run `python -m app.load_orders` first. |

```json
{
  "error": "invalid_query",
  "message": "Only SELECT queries are allowed.",
  "sql": "DROP TABLE orders"
}
```

## Tests

```bash
python check.py
```

Runs the style check (ruff) and the tests (pytest). The tests need no API key and send
no request: the LLM is always replaced by a fake. GitHub Actions runs the same command
on every push, on Linux with Python 3.12.

| File | What it covers |
|------|----------------|
| [`tests/test_cleaning.py`](tests/test_cleaning.py) | **The cleaning**: each rule on hand-written rows, and the exact counts on the generated file |
| [`tests/test_validator.py`](tests/test_validator.py) | **The query validation**: 10 queries that must pass, 24 that must be rejected with a reason, the row limit |
| [`tests/test_api.py`](tests/test_api.py) | **The endpoint with the LLM mocked**: a correct answer, destructive SQL, a forbidden table, text that is not SQL, an LLM failure, a missing database |
| [`tests/test_llm.py`](tests/test_llm.py) | The LLM client with the SDK replaced by a fake: refusals, cut-off answers, network errors, a missing key |
| [`tests/test_views.py`](tests/test_views.py) | The two views on a small hand-written data set |
| [`tests/test_generate_data.py`](tests/test_generate_data.py) | The generator: row counts, the three kinds of error, reproducibility |
| [`tests/test_evals.py`](tests/test_evals.py) | The evaluation tooling: every reference query is valid and returns data, and the result comparison is fair |

## Evaluation

The tests show the code handles every kind of LLM answer. They do not show that the
real model writes correct SQL. That is measured separately:

```bash
python -m evals.run --report evals/REPORT.md
```

This sends the 28 cases in [`evals/questions.json`](evals/questions.json) to the real
model through the endpoint. It needs `LLM_API_KEY` and every run is billed by the
provider, so it is not part of `check.py` or CI.

- **22 questions about the data**, in Spanish and English. Each has a reference query
  written by hand. A case passes when the endpoint's rows hold the same values as the
  reference rows: the result is compared, not the SQL text, since many queries are right.
- **6 requests that must be refused**: delete or change data, read a system table, an
  off-topic question, data the tables do not have, and a prompt injection. A case
  passes when the endpoint answers with an error and runs nothing.

Latest result with `gpt-5-mini`, in [`evals/REPORT.md`](evals/REPORT.md): **28/28**,
median latency 3.6 seconds. How to read that number:

- The first run scored 26/28. One failure was the model's: asked for the customers who
  "buy the most", it ranked by number of orders instead of money spent. The prompt now
  states the definition. The other was mine: the question "which is the largest order"
  had three tied orders and a reference answer of one row, so the case was reworded.
- After those two changes it scored 28/28 twice in a row. Because the prompt was
  adjusted with these same questions, 28/28 is not an unbiased accuracy estimate: it
  says these cases work, not that 100% of new questions will.

## Project layout

```
app/
  generate_data.py   writes the raw CSV with deliberate errors
  cleaning.py        cleaning rules (pure function, no disk access)
  load_orders.py     reads the CSV, loads SQLite, creates the views
  sql/views.sql      the two views
  validator.py       checks the LLM's SQL on its syntax tree
  llm.py             prompt and LLM client behind a small interface
  db.py              read-only connection with a time limit
  config.py          settings read from the environment and `.env`
  main.py            FastAPI app with POST /ask
tests/               the tests, listed in the table above
evals/               questions with reference answers, the runner and the last report
AGENTS.md            rules the AI assistant works under
DECISIONS.md         every decision and its reason
docs/ai-log.md       what I asked the AI, accepted and corrected, step by step
check.py             the single verification command
```

## Decisions

The full list, with the reasoning, is in [DECISIONS.md](DECISIONS.md). The ones that
shape the project:

- **SQLite.** No server to install, so the project runs after one `pip install`, and
  it can open a database read-only.
- **An `order_id` column** is added to the six fields in the statement, so "duplicate"
  means the same order appearing twice.
- **Cleaning never drops a row silently.** Duplicates keep one row per order. Dates
  are rewritten as ISO from an explicit list of formats, read as day first. A row whose
  date cannot be recovered is dropped and counted. A row with an empty amount is kept
  with `NULL`: the order happened, and `SUM` ignores `NULL`, so sales are not distorted.
- **A sale is a `completed` order.** Pending, cancelled and refunded orders are not
  revenue. The views apply the rule. The LLM can also query the `orders` table
  directly; there the rule is stated in the prompt, which the model is asked to follow
  but nothing enforces.
- **The LLM's SQL is treated as untrusted input.** It is parsed with sqlglot and
  checked on its syntax tree, not with text matching: one statement, a `SELECT`, only
  the allowed tables, a row limit of 200. Text matching would reject a product named
  "Update" and miss `SELECT ...; DROP TABLE ...` written creatively.
- **Two barriers, not one.** Behind the validator, the API opens SQLite read-only and
  stops any query after 2 seconds. A test runs a `DELETE` on that connection without
  the validator and checks that SQLite refuses it.
- **Each failure has its own error code**, and the response shows the SQL involved
  whenever the LLM got as far as writing one. For a tool that answers business
  questions, seeing how a number was computed matters as much as the number.
- **The LLM sits behind a small interface.** That is what lets the tests mock it, and
  it is why changing provider late in the project touched one module.
- **The prompt carries the real values in the database** (countries, statuses,
  products, date range). That is how "España" becomes `'Spain'`.

## What I would do with more time

- **A larger evaluation with a held-out part.** The 28 cases were also used to adjust
  the prompt, so their score is optimistic. I would add questions the prompt has never
  been tuned on, harder ones (comparisons between periods, questions with two
  readings), and use the set to compare models and prompts by cost and accuracy.
- **Let the model correct itself once.** When the SQL fails validation or execution,
  send the error back to the LLM for one retry before answering with an error.
- **Stricter validation.** Replace the function denylist with an allowlist, check that
  columns exist before running, and estimate query cost instead of relying only on
  the time limit.
- **Dates across several years.** The data covers 2025 only, so "in March" has one
  answer. With more years the API should ask which one, or state the year it assumed.
- **Conflicting duplicates.** Two rows with the same `order_id` and different content
  are not handled: the first one wins. A real source needs a rule, such as the most
  recent row, and a report of the conflicts.
- **Production concerns.** Authentication and rate limiting on the endpoint, structured
  logs of each question with its SQL, latency and token cost, and a cache for repeated
  questions.
- **PostgreSQL with a read-only role**, so the second barrier is a database permission
  instead of a connection flag.
- **DeepSeek is supported by configuration but was not run.** I would run the
  evaluation on it and compare it with OpenAI.

## How I used AI

I built this project with Claude Code, an AI coding assistant, working under rules I
set. The assistant wrote the code, the tests and the first draft of the documentation;
I directed the work, made the decisions below and accepted or changed what it proposed.
The step-by-step record is in [docs/ai-log.md](docs/ai-log.md).

**How I set it up.** I maintain my own harness for AI coding agents,
[ai-harness-framework](https://github.com/maideps/ai-harness-framework). Installing it
in full would have added more harness than project, so I applied its method in a light
form: [AGENTS.md](AGENTS.md) holds the rules the assistant follows (one feature at a
time, verify before saying "done", one commit per logical change, decisions written
down), [check.py](check.py) is the single verification command, and
[DECISIONS.md](DECISIONS.md) records why each choice was made.

**What I asked for.** First a plan from the statement, then one feature at a time in
the order of the assignment: generator, cleaning and load, views, validator, endpoint,
README. Midway I asked for a rule on how the assistant writes commit messages, because
the history is part of what this project shows.

**What I accepted.** The stack (SQLite, pandas, sqlglot, FastAPI), the order of the
steps, and several things the assistant proposed beyond the statement: the `order_id`
column, the cleaning report with a count per rule, counting only completed orders as
sales, the read-only connection as a second barrier, the query time limit, and a
separate error code for each failing step.

**What I corrected or decided against its first version.**

- The assistant first wrote the project files in Spanish, the language I was chatting
  in. I had everything inside the repository changed to English.
- It built the LLM client for the Anthropic API without asking which key I had. I
  have OpenAI and DeepSeek keys, so I chose to replace that client instead of keeping
  both, because I did not want code in the repository that had never run against a
  real model.
- I asked whether my harness should be used here. The assistant advised against
  installing it in full and proposed the light version, which I took.

**What the tests did not catch, and running it did.**

- With the LLM mocked, every test passed. Calling the endpoint with the real client
  and no key returned a 500, because the SDK raised an error type the code did not
  expect. That became a clear 502 and a new set of tests.
- The first run against a real model showed refusals reported as an LLM failure. They
  now have their own error code.

Both were found by running the real thing, not by reading the code. That is the main
thing I take from this: mocked tests show the code agrees with itself, and the
assistant's work still has to be run against reality before it is called done.

**What was verified, and what was not.** The endpoint was run against a real model
with my own key. In a first pass of nine questions, the six that have an answer were
recomputed with pandas, without SQL; the other three were refusals. Then I asked for
an evaluation set: 28 cases with reference answers, which scored
26/28 and, after one prompt fix and one corrected case, 28/28 twice. That score is
optimistic, for the reason given in [Evaluation](#evaluation). DeepSeek was not run.
