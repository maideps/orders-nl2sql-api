"""Tests for OpenAISqlGenerator with the SDK client replaced by a fake.

They cover how each kind of LLM outcome is turned into SQL text or into an LLMError.
No test here sends a request.
"""

from types import SimpleNamespace

import httpx
import openai
import pytest

from app.llm import CANNOT_ANSWER, LLMError, OpenAISqlGenerator, QuestionNotAnswerableError

DATA = {
    "countries": ["Spain"],
    "statuses": ["completed"],
    "products": ["Laptop"],
    "date_range": ["2025-01-01", "2025-12-31"],
}


def _generator(outcome) -> OpenAISqlGenerator:
    """Build a generator whose client returns `outcome`, or raises it if it is an error."""

    def create(**kwargs):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return OpenAISqlGenerator(model="test-model", client=client)


def _response(content: str | None, finish_reason: str = "stop", refusal: str | None = None):
    message = SimpleNamespace(content=content, refusal=refusal)
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish_reason, message=message)])


def test_sql_text_is_returned_without_code_fences():
    generator = _generator(_response("```sql\nSELECT COUNT(*) FROM orders\n```"))

    assert generator.generate_sql("How many orders?", DATA) == "SELECT COUNT(*) FROM orders"


def test_missing_api_key_becomes_a_clear_llm_error(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    with pytest.raises(LLMError, match="Set LLM_API_KEY"):
        OpenAISqlGenerator().generate_sql("How many orders?", DATA)


def test_network_failure_becomes_an_llm_error():
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    sdk_error = openai.APIConnectionError(request=request)

    with pytest.raises(LLMError, match="APIConnectionError"):
        _generator(sdk_error).generate_sql("How many orders?", DATA)


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (_response(None, finish_reason="content_filter"), "declined"),
        (_response(None, refusal="I can't help with that."), "declined"),
        (_response("SELECT * FROM ord", finish_reason="length"), "cut off"),
        (_response(None), "empty answer"),
        (_response("   "), "empty answer"),
        (SimpleNamespace(choices=[]), "empty answer"),
    ],
)
def test_unusable_answers_become_llm_errors(response, message):
    with pytest.raises(LLMError, match=message):
        _generator(response).generate_sql("What is the weather?", DATA)


def test_the_cannot_answer_reply_is_not_an_llm_failure():
    with pytest.raises(QuestionNotAnswerableError):
        _generator(_response(CANNOT_ANSWER)).generate_sql("What is the weather?", DATA)
