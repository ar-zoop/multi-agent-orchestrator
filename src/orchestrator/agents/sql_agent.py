import logging
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date, datetime
from pathlib import Path

from orchestrator.agents.sql_safety import UnsafeSQLError, make_safe, validate_sql
from orchestrator.core.chat_message import Message
from orchestrator.core.chat_request import ChatRequest

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"

DEFAULT_MAX_ROWS = 200
ROWS_SHOWN_TO_MODEL = 40

SYSTEM_PROMPT_TEMPLATE = """You are a SQL assistant for a fintech loan servicing system \
(a Postgres database covering borrowers, loans, payments, and a general ledger).

Given a natural-language question, write exactly one PostgreSQL query that answers it.

Rules:
- Only ever write SELECT statements. Never write INSERT, UPDATE, DELETE, DROP, ALTER, \
or any statement that modifies data or schema.
- Use only the tables and columns defined in the schema below - do not invent columns.
- Never include SQL comments and never write more than one statement.
- Return ONLY the SQL query. No explanation, no markdown code fences, no commentary.

Schema:
{schema}
"""

ANSWER_PROMPT_TEMPLATE = """You are a fintech analyst. Answer the user's question using \
only the query results below. Be concise and factual, quote the concrete numbers, and do \
not invent data that is not in the results. If the result set is empty, say so plainly.

Question:
{question}

SQL that was executed:
{sql}

Results ({row_count} row(s){truncation_note}):
{table}
"""


class SqlAgentError(RuntimeError):
    pass


@dataclass
class SqlResult:
    sql: str
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False


@dataclass
class SqlAnswer:
    question: str
    sql: str
    result: SqlResult
    answer: str


def _load_schema() -> str:
    return _SCHEMA_PATH.read_text()


def build_sql_request(question: str, model: str, temperature: float = 0.0) -> ChatRequest:
    return ChatRequest(
        model=model,
        messages=[
            Message(role="system", content=SYSTEM_PROMPT_TEMPLATE.format(schema=_load_schema())),
            Message(role="user", content=question),
        ],
        temperature=temperature,
    )


def _strip_code_fences(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def generate_sql(question: str, provider, model: str) -> str:
    response = provider.complete(build_sql_request(question, model=model))
    return _strip_code_fences(response.content)


def _render_cell(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, Decimal):
        return f"{value:f}"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def render_table(result: SqlResult, max_rows: int = ROWS_SHOWN_TO_MODEL) -> str:
    if not result.columns:
        return "(no columns returned)"
    if not result.rows:
        return " | ".join(result.columns) + "\n(no rows)"

    shown = result.rows[:max_rows]
    header = " | ".join(result.columns)
    separator = "-" * len(header)
    body = "\n".join(" | ".join(_render_cell(c) for c in row) for row in shown)
    table = f"{header}\n{separator}\n{body}"
    if len(result.rows) > len(shown):
        table += f"\n... {len(result.rows) - len(shown)} more row(s) not shown"
    return table


def execute_sql(sql: str, connection_factory=None, max_rows: int = DEFAULT_MAX_ROWS) -> SqlResult:
    if connection_factory is None:
        from orchestrator.db.connection import read_only_connection

        connection_factory = read_only_connection

    safe_sql = make_safe(sql, max_rows=max_rows)
    logger.info("executing sql: %s", safe_sql)

    with connection_factory() as conn:
        with conn.cursor() as cur:
            cur.execute(safe_sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = list(cur.fetchmany(max_rows + 1))

    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    return SqlResult(
        sql=safe_sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
    )


def build_answer_request(question: str, result: SqlResult, model: str,
                         temperature: float = 0.0) -> ChatRequest:
    truncation_note = ", truncated" if result.truncated else ""
    prompt = ANSWER_PROMPT_TEMPLATE.format(
        question=question,
        sql=result.sql,
        row_count=result.row_count,
        truncation_note=truncation_note,
        table=render_table(result),
    )
    return ChatRequest(
        model=model,
        messages=[
            Message(role="system", content="You explain SQL query results in plain English."),
            Message(role="user", content=prompt),
        ],
        temperature=temperature,
    )


def summarise_result(question: str, result: SqlResult, provider, model: str) -> str:
    response = provider.complete(build_answer_request(question, result, model=model))
    return (response.content or "").strip()


def answer_question(question: str, provider, model: str, connection_factory=None,
                    max_rows: int = DEFAULT_MAX_ROWS) -> SqlAnswer:
    sql = generate_sql(question, provider, model=model)
    try:
        validate_sql(sql)
    except UnsafeSQLError as e:
        logger.warning("rejected generated sql: %s", sql)
        raise SqlAgentError(f"Generated SQL was rejected by the safety guard: {e}") from e

    result = execute_sql(sql, connection_factory=connection_factory, max_rows=max_rows)
    answer = summarise_result(question, result, provider, model=model)
    return SqlAnswer(question=question, sql=result.sql, result=result, answer=answer)
