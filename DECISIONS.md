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
switching providers changes a single file (this happened: see D-010).

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

## D-007 · What the views count as a sale

- **Only orders with status `completed` are sales.** Pending orders may never be paid,
  and cancelled or refunded ones brought in no money. Counting every status would
  overstate revenue. The rule lives in the views, so every question answered through
  them uses the same definition.
- **"Customers who buy the most" is ranked by money spent**, not by number of orders.
  The view also returns the order count, so the other reading is one `ORDER BY` away.
  Ties are broken by customer name to keep the result stable.
- **The views live in a `.sql` file** (`app/sql/views.sql`), not in Python strings, so
  they can be read and reviewed as SQL. The load script recreates them on every run.

## D-008 · What the query validator accepts

The LLM output is untrusted input. A query runs only if it passes all of these checks,
made on the parsed syntax tree (see D-002):

1. **One statement.** `SELECT ...; DROP TABLE ...` is rejected, not truncated.
2. **The statement is a `SELECT`** (or a `UNION`/`INTERSECT`/`EXCEPT` of them). The
   check is an allowlist of statement types, so anything else — `INSERT`, `PRAGMA`,
   `ATTACH`, `VACUUM`, syntax sqlglot does not know — fails by default.
3. **No write or escape clause inside it**, such as `SELECT ... INTO`.
4. **Every table is in the allowlist**: `orders` and the two views. Names defined by a
   `WITH` clause in the same query are accepted. Schema-qualified names (`main.orders`),
   table-valued functions and any `sqlite_*` name are rejected, the last one even when
   a `WITH` clause defines it, because that could hide a read of the real system table.
5. **No function that loads code or reads files** (`load_extension`, `readfile`, ...).
   This is a denylist, the weakest check here: it only covers the functions I know of.
6. **A row limit.** `LIMIT 200` is added when missing and lowered when higher, so one
   question cannot return the whole table.

The validator returns the SQL regenerated by sqlglot. A test runs every accepted query
on SQLite after validation, to catch a rewrite that changes or breaks the query.

Known limits: the validator does not check that columns exist (SQLite reports that at
execution) and does not bound query cost, so a heavy self-join is accepted.

## D-009 · The question endpoint

- **One endpoint, `POST /ask`, with four separate steps**: the LLM writes SQL, the
  validator checks it, SQLite runs it read-only, the rows are returned. Each step has
  its own error, so a caller can tell what went wrong:

  | Status | `error` | Meaning |
  |--------|---------|---------|
  | 422 | `invalid_query` | The LLM's SQL broke a validator rule. It was not run. |
  | 422 | `query_execution_failed` | The SQL was valid but SQLite rejected it (for example an unknown column) or it ran out of time. |
  | 422 | `question_not_answerable` | The LLM replied that the orders data cannot answer the question (off-topic, or a request to change data). |
  | 502 | `llm_error` | The LLM call failed, was declined, was cut off or came back empty. |
  | 503 | `database_not_found` | The load script has not been run. |

- **The response includes the SQL that ran**, and error responses include the SQL the
  LLM wrote. For a tool that answers business questions, being able to see how a number
  was computed matters as much as the number.
- **Second barrier: a read-only connection.** The API opens SQLite with `mode=ro`, so
  even a query that got past the validator cannot write. A test runs a `DELETE`
  straight on that connection, without the validator, and checks SQLite refuses it.
- **Queries are stopped after 2 seconds** with SQLite's progress handler. This covers
  the cost limit the validator does not have.
- **The prompt carries the real values from the database** (countries, statuses,
  products, date range), read on each request. That is how "España" becomes
  `'Spain'` and "marzo" becomes `2025-03` without hard-coding the data in the prompt.
- **The LLM is asked for plain SQL, not JSON.** Its answer is untrusted either way and
  goes through the validator; a JSON wrapper would add a parsing step and no safety. A
  fixed `CANNOT_ANSWER` reply lets the model decline instead of inventing a query.
- **The endpoint does not turn rows into a sentence.** It returns columns and rows. A
  second LLM call to phrase the answer would double cost and latency and add a place
  where a number can be misreported.
- **Provider and model**: see D-010.

## D-010 · LLM provider: OpenAI-compatible API instead of Claude

The first version of the LLM client used the Anthropic API. I had no Anthropic API key
to test it with (a Claude subscription seat does not include API access), and I did not
want code in the repository that had never run against a real model. I do have OpenAI
and DeepSeek keys, so the client was rewritten for them.

- **One client for both providers.** DeepSeek follows the OpenAI chat-completions
  format, so the same code serves both: `LLM_BASE_URL` and `LLM_MODEL` select the
  provider. OpenAI is the default because it is the key a reviewer most likely has.
- **Provider-neutral setting names** (`LLM_API_KEY`, not `OPENAI_API_KEY`), since the
  key may belong to another provider.
- **The change touched one module and its tests.** The endpoint, the validator and the
  endpoint tests did not change, which is what the `SqlGenerator` interface in D-003
  was for.
- **Only the chat-completions parameters every compatible provider accepts are sent**
  (model and messages). No temperature or token limit, because providers and model
  families disagree on which of those they accept.
- **Checked against the real model.** Nine questions were sent through the endpoint
  with `gpt-5-mini`: six about the data, in Spanish and English, and three that should
  be refused (delete orders, the weather, read `sqlite_master`). The six returned
  correct results, checked against the database, in 2 to 6 seconds each; the three
  were refused by the model itself. Nine questions show the pipeline works; they are
  not a measure of accuracy.
- **A question the data cannot answer is a 422, not a 502.** The first real run showed
  those three refusals coming back as `llm_error`, as if the provider had failed. The
  model had worked and declined correctly, so the case got its own error,
  `question_not_answerable`.
- **Choosing the model is a measurement, not a guess.** The default is a small model
  because the task is a short translation. Picking between models should come from
  running a set of real questions with known answers, which this project does not
  have yet.
