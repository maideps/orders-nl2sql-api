"""Validation of SQL written by the LLM, before anything is executed.

The query is parsed with sqlglot and checked on its syntax tree, not with text
matching. A query is accepted only if it is a single read-only statement over the
allowed tables. `validate_query` returns the SQL to execute, with a row limit applied.
"""

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

ALLOWED_TABLES = frozenset({"orders", "sales_by_month_country", "top_10_customers"})
MAX_ROWS = 200

# Statements and clauses that write, change the schema or reach outside the database
FORBIDDEN_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Into,
    exp.Pragma,
    exp.Attach,
    exp.Detach,
    exp.Command,
)

# SQLite functions that load code or touch files. `pragma_*` functions expose settings.
FORBIDDEN_FUNCTIONS = frozenset({"load_extension", "readfile", "writefile", "edit"})
FORBIDDEN_FUNCTION_PREFIX = "pragma_"


class QueryValidationError(ValueError):
    """The query is not allowed. The message says which rule it broke."""


def validate_query(sql: str) -> str:
    """Return the safe SQL to run, or raise QueryValidationError."""
    statement = _parse_single_statement(sql)

    if not isinstance(statement, (exp.Select, exp.SetOperation)):
        raise QueryValidationError("Only SELECT queries are allowed.")

    for node in statement.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise QueryValidationError(
                f"Only read-only queries are allowed: found {node.key.upper()}."
            )
        if isinstance(node, exp.Func):
            _check_function(node)

    _check_tables(statement)
    return _apply_row_limit(statement).sql(dialect="sqlite")


def _parse_single_statement(sql: str) -> exp.Expression:
    if not sql or not sql.strip():
        raise QueryValidationError("The query is empty.")
    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except SqlglotError as error:
        raise QueryValidationError(f"The query is not valid SQL: {error}") from error
    if len(statements) != 1:
        raise QueryValidationError("Exactly one SQL statement is allowed.")
    return statements[0]


def _check_function(function: exp.Func) -> None:
    name = function.name.lower() if isinstance(function, exp.Anonymous) else function.key
    if name in FORBIDDEN_FUNCTIONS or name.startswith(FORBIDDEN_FUNCTION_PREFIX):
        raise QueryValidationError(f"Function not allowed: {name}.")


def _check_tables(statement: exp.Expression) -> None:
    """Every table must be an allowed one, or a CTE defined inside the query."""
    cte_names = {cte.alias.lower() for cte in statement.find_all(exp.CTE)}

    for table in statement.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise QueryValidationError("Table-valued functions are not allowed.")
        name = table.name.lower()
        # A CTE named like a system table could hide a read of the real one in another
        # part of the query, so `sqlite_*` names are rejected even when a CTE defines them.
        if name.startswith("sqlite_"):
            raise QueryValidationError(f"Table not allowed: {name}.")
        if table.db or table.catalog:
            raise QueryValidationError(f"Schema-qualified tables are not allowed: {table.sql()}.")
        if name not in ALLOWED_TABLES and name not in cte_names:
            raise QueryValidationError(f"Table not allowed: {name}.")


def _apply_row_limit(statement: exp.Expression) -> exp.Expression:
    """Add LIMIT when it is missing, and lower it when it is above MAX_ROWS."""
    limit = statement.args.get("limit")
    current = limit.expression if limit is not None else None
    within_bounds = (
        isinstance(current, exp.Literal) and current.is_int and int(current.this) <= MAX_ROWS
    )
    return statement if within_bounds else statement.limit(MAX_ROWS)
