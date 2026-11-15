# AI usage log

Tool: Claude Code. One entry per step: what I asked for, what I accepted and what I
corrected. This log feeds the "How I used AI" section of the README.

## 0 · Planning and project structure

- **What I asked for**: a plan for the assignment based on its statement, whether my
  ai-harness-framework was worth using here, and a name for the project. Then the
  initial structure.
- **What I accepted**: the proposed stack (SQLite, pandas, sqlglot, FastAPI), the order
  of steps with one commit per feature, and the name `orders-nl2sql-api`.
- **What I decided myself**: to use a lightweight version of the harness instead of
  installing it in full, to show how I work with AI without filling the repository with
  harness files.
- **What I corrected**: the first version of the project files was written in Spanish;
  I asked for everything inside the project to be in English.

## 1b · Commit message rule

- **What I asked for**: a rule the LLM must follow when it writes commits, after seeing
  the first two commit messages.
- **What I accepted**: the rule in `AGENTS.md`, based on the `commit` skill of my
  ai-harness-framework, with extra limits on habits LLMs have (listing files, praise
  words, claiming checks that did not run).
- **Gap found afterwards**: the AI pointed out that Claude Code reads `CLAUDE.md`, not
  `AGENTS.md`, so the rule was not loaded on its own. I approved adding a `CLAUDE.md`
  that imports it.

## 1 · Raw data generator

- **What I asked for**: the script that generates the orders CSV with the deliberate
  errors the assignment lists.
- **What the AI proposed beyond the request**: an `order_id` column, a fixed seed, exact
  error rates per type, and a small test for the generator (see D-005).

## 2 · Cleaning and load into SQLite

- **What I asked for**: the script that cleans the CSV and stores it in SQLite, with a
  test for the cleaning.
- **What the AI proposed beyond the request**: keeping rows with an empty amount as
  NULL instead of dropping them, an explicit list of date formats read as day first,
  and a printed report with a count per rule (see D-006).

## 3 · SQL views

- **What I asked for**: the two views, sales by month and country and the top 10
  customers.
- **What the AI proposed beyond the request**: counting only `completed` orders as
  sales, ranking customers by money spent, keeping the SQL in its own file and adding
  tests for the views (see D-007).

## 4 · Query validator

- **What I asked for**: validation of the SQL before it runs: read-only and allowed
  tables only, with a test.
- **How the AI worked**: before writing the validator it ran a probe script to see how
  the installed sqlglot version parses about twenty safe and unsafe queries, and wrote
  the checks from that output instead of from memory.
- **What the AI proposed beyond the request**: rejecting multiple statements,
  schema-qualified names, table-valued functions and `sqlite_*` names; a function
  denylist; and an enforced row limit (see D-008).
- **What the AI checked afterwards**: that the SQL returned by the validator gives the
  same result as the original query on the real database, for five sample queries.
