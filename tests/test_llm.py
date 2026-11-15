"""Tests for ClaudeSqlGenerator with the Anthropic client replaced by a fake.

They cover how each kind of LLM outcome is turned into SQL text or into an LLMError.
No test here sends a request.
"""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.llm import CANNOT_ANSWER, ClaudeSqlGenerator, LLMError

DATA = {
    "countries": ["Spain"],
    "statuses": ["completed"],
    "products": ["Laptop"],
    "date_range": ["2025-01-01", "2025-12-31"],
}


def _generator(outcome) -> ClaudeSqlGenerator:
    """Build a generator whose client returns `outcome`, or raises it if it is an error."""

    def create(**kwargs):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    return ClaudeSqlGenerator(model="test-model", client=client)


def _response(text: str, stop_reason: str = "end_turn"):
    blocks = [
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="text", text=text),
    ]
    return SimpleNamespace(stop_reason=stop_reason, content=blocks)


def test_sql_text_is_returned_without_thinking_blocks_or_fences():
    generator = _generator(_response("```sql\nSELECT COUNT(*) FROM orders\n```"))

    assert generator.generate_sql("How many orders?", DATA) == "SELECT COUNT(*) FROM orders"


def test_missing_credentials_become_a_clear_llm_error():
    sdk_error = TypeError('"Could not resolve authentication method. Expected one of api_key..."')

    with pytest.raises(LLMError, match="credentials are not configured"):
        _generator(sdk_error).generate_sql("How many orders?", DATA)


def test_an_unrelated_type_error_is_not_hidden():
    with pytest.raises(TypeError, match="unexpected keyword"):
        _generator(TypeError("unexpected keyword argument")).generate_sql("How many?", DATA)


def test_network_failure_becomes_an_llm_error():
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    sdk_error = anthropic.APIConnectionError(request=request)

    with pytest.raises(LLMError, match="APIConnectionError"):
        _generator(sdk_error).generate_sql("How many orders?", DATA)


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (_response("", stop_reason="refusal"), "declined"),
        (_response("SELECT * FROM ord", stop_reason="max_tokens"), "cut off"),
        (_response("   "), "empty answer"),
        (_response(CANNOT_ANSWER), "could not answer"),
    ],
)
def test_unusable_answers_become_llm_errors(response, message):
    with pytest.raises(LLMError, match=message):
        _generator(response).generate_sql("What is the weather?", DATA)
