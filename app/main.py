"""FastAPI application: ask a question in natural language, get rows back.

Run with: uvicorn app.main:app --reload

Flow of POST /ask:
    question -> LLM writes SQL -> validator -> read-only execution -> JSON result

Every failure has its own status code and a machine-readable `error` code:
    422 invalid_query            the LLM's SQL broke a validation rule; it was not run
    422 query_execution_failed   the SQL passed validation but SQLite rejected it
    422 question_not_answerable  the LLM said the orders data cannot answer the question
    502 llm_error                the LLM failed, declined or returned an empty answer
    503 database_not_found       the load script has not been run yet
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import DB_PATH
from app.db import DatabaseNotFoundError, QueryExecutionError, describe_data, run_query
from app.llm import LLMError, OpenAISqlGenerator, QuestionNotAnswerableError, SqlGenerator
from app.validator import QueryValidationError, validate_query

app = FastAPI(
    title="Orders NL2SQL API",
    description="Answers natural-language questions about orders with validated SQL.",
)


class AskRequest(BaseModel):
    question: str = Field(
        min_length=3, max_length=500, examples=["¿Cuánto vendimos en España en marzo?"]
    )


class AskResponse(BaseModel):
    question: str
    sql: str = Field(description="The validated SQL that was executed")
    columns: list[str]
    rows: list[list]
    row_count: int


class ErrorResponse(BaseModel):
    error: str = Field(description="Machine-readable error code")
    message: str
    sql: str | None = Field(default=None, description="The SQL the LLM wrote, when there is one")


@lru_cache
def get_sql_generator() -> SqlGenerator:
    return OpenAISqlGenerator()


def get_db_path() -> Path:
    return DB_PATH


def _error(status_code: int, error: str, message: str, sql: str | None = None) -> JSONResponse:
    body = ErrorResponse(error=error, message=message, sql=sql)
    return JSONResponse(status_code=status_code, content=body.model_dump())


@app.post(
    "/ask",
    response_model=AskResponse,
    responses={422: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 503: {}},
)
def ask(
    request: AskRequest,
    generator: Annotated[SqlGenerator, Depends(get_sql_generator)],
    db_path: Annotated[Path, Depends(get_db_path)],
):
    try:
        data = describe_data(db_path)
    except DatabaseNotFoundError as error:
        return _error(503, "database_not_found", str(error))

    try:
        generated_sql = generator.generate_sql(request.question, data)
    except LLMError as error:
        return _error(502, "llm_error", str(error))
    except QuestionNotAnswerableError as error:
        return _error(422, "question_not_answerable", str(error))

    try:
        safe_sql = validate_query(generated_sql)
    except QueryValidationError as error:
        return _error(422, "invalid_query", str(error), sql=generated_sql)

    try:
        columns, rows = run_query(safe_sql, db_path)
    except QueryExecutionError as error:
        return _error(422, "query_execution_failed", str(error), sql=safe_sql)

    return AskResponse(
        question=request.question, sql=safe_sql, columns=columns, rows=rows, row_count=len(rows)
    )
