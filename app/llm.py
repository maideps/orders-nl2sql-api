"""Turn a natural-language question into SQL with an LLM.

The API depends on the `SqlGenerator` interface, not on a provider. `OpenAISqlGenerator`
is the real implementation; tests replace it with a fake that never touches the network.
It talks to any API that follows the OpenAI chat format, so OpenAI and DeepSeek both
work by changing settings in `.env`.

Whatever the LLM returns is untrusted text. This module only extracts it: the decision
to run it belongs to `app.validator`.
"""

import os
from typing import Protocol

import openai

DEFAULT_MODEL = "gpt-5-mini"
REQUEST_TIMEOUT_SECONDS = 30.0
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
- Give every column that is not a plain table column a short snake_case alias with AS,
  for example SUM(amount) AS total_sales. The alias is the column name the caller sees.
- Reply with the SQL only: no explanation, no markdown, no code fences.
- If the question cannot be answered from these tables, reply with exactly
  {cannot_answer}
"""


class LLMError(Exception):
    """The LLM call failed or returned nothing usable. The message is safe to show."""


class QuestionNotAnswerableError(Exception):
    """The LLM worked and said the question cannot be answered from the orders data."""


class SqlGenerator(Protocol):
    def generate_sql(self, question: str, data: dict[str, list[str]]) -> str:
        """Return the SQL text, or raise LLMError or QuestionNotAnswerableError."""


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


class OpenAISqlGenerator:
    """SqlGenerator for any API that follows the OpenAI chat-completions format.

    Settings come from the environment (loaded from `.env`):
      LLM_API_KEY   required
      LLM_BASE_URL  optional; set it to use another provider, e.g. https://api.deepseek.com
      LLM_MODEL     optional; defaults to DEFAULT_MODEL
    """

    def __init__(self, model: str | None = None, client: openai.OpenAI | None = None):
        self.model = model or os.getenv("LLM_MODEL") or DEFAULT_MODEL
        self._client = client

    def _get_client(self) -> openai.OpenAI:
        # Created on first use, so the API starts without a key and tests need none
        if self._client is None:
            api_key = os.getenv("LLM_API_KEY")
            if not api_key:
                raise LLMError("The LLM credentials are not configured. Set LLM_API_KEY in .env.")
            self._client = openai.OpenAI(
                api_key=api_key,
                base_url=os.getenv("LLM_BASE_URL") or None,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        return self._client

    def generate_sql(self, question: str, data: dict[str, list[str]]) -> str:
        client = self._get_client()
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": build_system_prompt(data)},
                    {"role": "user", "content": question},
                ],
            )
        except openai.OpenAIError as error:
            # Covers a rejected key, an unknown model, rate limits, timeouts and server errors
            raise LLMError(f"The LLM request failed: {type(error).__name__}.") from error

        if not response.choices:
            raise LLMError("The LLM returned an empty answer.")
        choice = response.choices[0]
        if choice.finish_reason == "content_filter" or getattr(choice.message, "refusal", None):
            raise LLMError("The LLM declined to answer this question.")
        if choice.finish_reason == "length":
            raise LLMError("The LLM answer was cut off before it finished.")

        sql = extract_sql(choice.message.content or "")
        if not sql:
            raise LLMError("The LLM returned an empty answer.")
        if sql == CANNOT_ANSWER:
            raise QuestionNotAnswerableError(
                "This question cannot be answered from the orders data."
            )
        return sql
