"""Turn a natural-language question into SQL with an LLM.

The API depends on the `SqlGenerator` interface, not on a provider. `ClaudeSqlGenerator`
is the real implementation; tests replace it with a fake that never touches the network.

Whatever the LLM returns is untrusted text. This module only extracts it: the decision
to run it belongs to `app.validator`.
"""

import os
from typing import Protocol

import anthropic

DEFAULT_MODEL = "claude-opus-5-5"
CANNOT_ANSWER = "CANNOT_ANSWER"

SYSTEM_PROMPT_TEMPLATE = """\
You translate questions about an orders database into one SQLite query.

Tables you may read (nothing else exists for you):

orders: one row per order
  order_id TEXT, order_date TEXT (ISO YYYY-MM-DD), customer TEXT, country TEXT,
  product TEXT, amount REAL (may be NULL), status TEXT

sales_by_month_country: completed orders per month and country
  month TEXT (YYYY-MM), country TEXT, orders INTEGER, total_sales REAL

top_10_customers: the ten customers who spent the most (completed orders)
  customer TEXT, country TEXT, orders INTEGER, total_spent REAL

Values in the data:
- country: {countries}
- status: {statuses}
- product: {products}
- order_date runs from {first_date} to {last_date}

Rules:
- A sale is an order with status 'completed'. Questions about sales, revenue or money
  sold count only those orders.
- Questions may be in any language. Map names to the stored values, for example
  "España" is 'Spain' and "portátil" is 'Laptop'.
- When a question names a month without a year, use the year covered by the data.
- Write a single SELECT statement. Never write INSERT, UPDATE, DELETE, DDL or PRAGMA.
- Reply with the SQL only: no explanation, no markdown, no code fences.
- If the question cannot be answered from these tables, reply with exactly
  {cannot_answer}
"""


class LLMError(Exception):
    """The LLM call failed or returned nothing usable. The message is safe to show."""


class SqlGenerator(Protocol):
    def generate_sql(self, question: str, data: dict[str, list[str]]) -> str:
        """Return the SQL text for the question, or raise LLMError."""


def build_system_prompt(data: dict[str, list[str]]) -> str:
    first_date, last_date = data["date_range"]
    return SYSTEM_PROMPT_TEMPLATE.format(
        countries=", ".join(data["countries"]),
        statuses=", ".join(data["statuses"]),
        products=", ".join(data["products"]),
        first_date=first_date,
        last_date=last_date,
        cannot_answer=CANNOT_ANSWER,
    )


def extract_sql(text: str) -> str:
    """Remove a markdown code fence if the model added one despite the instructions."""
    sql = text.strip()
    if sql.startswith("```"):
        lines = sql.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        sql = "\n".join(lines).strip()
    return sql


class ClaudeSqlGenerator:
    """SqlGenerator backed by the Anthropic API.

    Credentials come from the environment (ANTHROPIC_API_KEY, loaded from `.env`).
    """

    def __init__(self, model: str | None = None, client: anthropic.Anthropic | None = None):
        self.model = model or os.getenv("ANTHROPIC_MODEL") or DEFAULT_MODEL
        self._client = client

    @property
    def client(self) -> anthropic.Anthropic:
        # Created on first use, so the API starts without a key and tests need none
        if self._client is None:
            self._client = anthropic.Anthropic(timeout=30.0)
        return self._client

    def generate_sql(self, question: str, data: dict[str, list[str]]) -> str:
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                # The task is a short translation: low effort keeps the answer fast
                output_config={"effort": "low"},
                # If a safety classifier declines, the API retries on a fallback model
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=build_system_prompt(data),
                messages=[{"role": "user", "content": question}],
            )
        except anthropic.AnthropicError as error:
            # Covers a rejected key, rate limits, timeouts and server errors
            raise LLMError(f"The LLM request failed: {type(error).__name__}.") from error
        except TypeError as error:
            # With no credentials at all the SDK raises TypeError before sending anything
            if "authentication" not in str(error):
                raise
            raise LLMError(
                "The LLM credentials are not configured. Set ANTHROPIC_API_KEY in .env."
            ) from error

        if response.stop_reason == "refusal":
            raise LLMError("The LLM declined to answer this question.")
        if response.stop_reason == "max_tokens":
            raise LLMError("The LLM answer was cut off before it finished.")

        text = "".join(block.text for block in response.content if block.type == "text")
        sql = extract_sql(text)
        if not sql:
            raise LLMError("The LLM returned an empty answer.")
        if sql == CANNOT_ANSWER:
            raise LLMError("The LLM could not answer this question from the orders data.")
        return sql
