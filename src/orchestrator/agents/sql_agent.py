from pathlib import Path

from orchestrator.core.chat_message import Message
from orchestrator.core.chat_request import ChatRequest

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"

SYSTEM_PROMPT_TEMPLATE = """You are a SQL assistant for a fintech loan servicing system \
(a Postgres database covering borrowers, loans, payments, and a general ledger).

Given a natural-language question, write exactly one PostgreSQL query that answers it.

Rules:
- Only ever write SELECT statements. Never write INSERT, UPDATE, DELETE, DROP, ALTER, \
or any statement that modifies data or schema.
- Use only the tables and columns defined in the schema below - do not invent columns.
- Return ONLY the SQL query. No explanation, no markdown code fences, no commentary.

Schema:
{schema}
"""


def _load_schema() -> str:
    return _SCHEMA_PATH.read_text()


def build_sql_request(question: str, model: str, temperature: float = 0.0) -> ChatRequest:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(schema=_load_schema())
    return ChatRequest(
        model=model,
        messages=[
            Message(role="system", content=system_prompt),
            Message(role="user", content=question),
        ],
        temperature=temperature,
    )


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]  # drop opening ``` or ```sql
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]  # drop closing ```
        text = "\n".join(lines).strip()
    return text


def generate_sql(question: str, provider, model: str) -> str:
    """Ask the model to translate a natural-language question into SQL.

    Returns just the query text. This is prompt design + generation only -
    actually executing the query against Postgres (with read-only safety
    guards) is a separate, later step, not done here.
    """
    request = build_sql_request(question, model=model)
    response = provider.complete(request)
    return _strip_code_fences(response.content)
