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

## 1 · Raw data generator

- **What I asked for**: the script that generates the orders CSV with the deliberate
  errors the assignment lists.
- **What the AI proposed beyond the request**: an `order_id` column, a fixed seed, exact
  error rates per type, and a small test for the generator (see D-005).
