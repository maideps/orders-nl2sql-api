# AI usage log

Tool: Claude Code. One entry per step: what I asked for, what I accepted and what I
corrected. This log feeds the "How I used AI" section of the README.

## 0 · Planning and project structure

- **What I asked for**: a plan for the assignment based on its statement, whether my
  ai-harness-framework was worth using here, and a name for the project. Then the
  initial structure.
- **What I accepted**: the proposed stack (SQLite, pandas, sqlglot, FastAPI), the order
  of steps with one commit per feature, and the name `orders-nl2sql-api`.
- **What I decided**: to use a lightweight version of the harness instead of
  installing it in full, as the AI advised when I asked, to show how I work with AI
  without filling the repository with harness files.
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

## 5 · Question endpoint and LLM client

- **What I asked for**: the FastAPI endpoint that takes a question, has an LLM write
  the query, validates it, runs it and returns the result, with clear errors and a
  test that mocks the LLM.
- **What the AI proposed beyond the request**: a read-only SQLite connection as a
  second barrier, a 2-second query timeout, a separate error code per failing step,
  returning the executed SQL, and feeding the prompt with real values from the
  database (see D-009).
- **A bug the tests did not catch**: all tests passed with the LLM mocked, but when the
  AI called the endpoint with the real client and no API key, the response was a 500.
  The SDK raises `TypeError`, not one of its own errors, when no credentials exist.
  The AI fixed it and added tests for the real client with the SDK replaced by a fake.
- **Not verified**: no request has been sent to the real model. No API key was
  available while this step was built, so the quality of the generated SQL is untested.

## 5b · Switching the LLM provider

- **What happened**: the AI built the LLM client for the Anthropic API, its own
  provider, without asking which key I had. I have no Anthropic API key, only OpenAI
  and DeepSeek ones.
- **What I corrected**: I chose to replace the Claude client with an OpenAI-compatible
  one, with OpenAI as the default, instead of keeping both and leaving a path in the
  repository that had never run against a real model (see D-010).
- **What it cost**: one module and its tests. The endpoint and its tests did not change.

## 5c · First run against a real model

- **What I asked for**: after adding my OpenAI key to `.env`, to run real questions
  through the endpoint.
- **What the AI did**: confirmed `.env` is ignored by git, listed the models my key can
  use to check the default exists, and sent nine questions (six answerable, three that
  must be refused).
- **Result**: the six answerable questions returned correct results and the three were
  refused. "¿Cuánto vendimos en España en marzo?" returns 2440.00, the value in the
  database.
- **What the run changed**: refusals came back as a 502 `llm_error`, which describes a
  provider failure that had not happened. The AI proposed and made a separate 422
  `question_not_answerable`. This was visible only with the real model: every mocked
  test passed before and after.
- **How the answers were checked**: the six results were recomputed with pandas on the
  cleaned data, without SQL, and all six match.
- **Limit**: nine hand-picked questions on one model. The three refusals never reached
  the validator, because the model declined first; the validator is covered by its
  own tests, not by this run.

## 6 · README

- **What I asked for**: the final README with how to run it, the decisions, what I
  would do with more time and how I used AI.
- **What the AI did**: wrote it from `DECISIONS.md` and this log, then cloned the
  repository into an empty folder and ran the README commands there to check they work
  from scratch.
- **What it corrected in its own draft**: two sentences in the AI section said more
  than what happened (who proposed the light harness, and who checked the answers).
