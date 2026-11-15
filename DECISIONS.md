# Decisions

A short log of technical decisions and the reason behind each one. It is updated in the
same commit as the code it affects.

## D-001 · SQLite as the database

The assignment allows PostgreSQL, SQLite or DuckDB. SQLite needs no installation and no
server, so the project runs after a single `pip install`. It can also open a connection
in read-only mode, which acts as a second barrier behind the validator.

## D-002 · Validate SQL on the syntax tree (sqlglot)

A list of forbidden words checked with regular expressions is easy to bypass and gives
false positives (for example, a product named "Update"). With `sqlglot` the query is
parsed and its structure is checked: a single statement, of type `SELECT`, reading only
from the allowed tables.

## D-003 · The LLM behind a small interface

The endpoint depends on a "question → SQL" function, not on a specific provider. The
endpoint test can then replace the LLM with a mock without touching the network, and
switching providers changes a single file.

## D-004 · Lightweight version of my AI harness

I work with my own agent harness
([ai-harness-framework](https://github.com/maideps/ai-harness-framework)). Here I apply
only its method (`AGENTS.md`, `check.py`, this file and `docs/ai-log.md`) and do not
install the full harness: it would add Node and state files to a Python project that
takes a few hours.

## D-005 · Shape of the generated data

- **An `order_id` column is added** to the six fields the assignment lists. It gives
  "duplicate" a precise meaning (the same order appearing twice) instead of relying on
  every field matching by chance.
- **The generator is seeded and the CSV is not committed.** Anyone gets the same file by
  running the script, and the repository holds no generated data.
- **Each error type is applied to a separate set of rows** (4% duplicates, 5% dates in
  another format, 2% impossible dates, 3% empty amounts), so the cleaning step can be
  checked against exact counts.
- **All orders fall in 2025.** A question such as "sales in March" then has one answer;
  handling several years is listed as future work.

## D-006 · Cleaning rules

- **Duplicates: one row per `order_id`, the first one seen.** In this data duplicates
  are exact copies, so which copy is kept does not matter. Two rows with the same id
  and different content would need a rule (for example, the most recent) that the
  assignment does not define.
- **Dates: rewritten as ISO `YYYY-MM-DD`.** The accepted formats are listed explicitly
  instead of letting a library guess, because guessing silently swaps day and month.
  Slash and dash dates are read as day first.
- **Unrecoverable dates: the row is dropped and counted.** An order without a date
  cannot be placed in any month, and inventing one would distort the sales views.
- **Empty amounts: the row is kept with `amount` as NULL.** The order did happen, so it
  still counts as an order; `SUM` ignores NULL, so it adds nothing to sales. Filling in
  a value (zero, an average) would change the totals without anyone noticing.
- **Nothing is dropped silently.** The script prints a report with the count for each
  rule, and a test checks those counts against the rates the generator uses.
- **The table is rebuilt on every run**, inside one transaction, so the load can be
  repeated and never leaves a half-written table.
