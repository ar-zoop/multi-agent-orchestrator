import json

from orchestrator.agents.code_review_agent import format_review, review_diff
from orchestrator.agents.sql_agent import DEFAULT_MAX_ROWS, answer_question, render_table
from orchestrator.core.tool import Tool
from orchestrator.core.tool_registry import ToolRegistry


def build_sql_tool(provider, model: str, connection_factory=None,
                   max_rows: int = DEFAULT_MAX_ROWS) -> Tool:
    def query_loan_database(question: str) -> str:
        answer = answer_question(
            question,
            provider=provider,
            model=model,
            connection_factory=connection_factory,
            max_rows=max_rows,
        )
        return json.dumps({
            "sql": answer.sql,
            "row_count": answer.result.row_count,
            "table": render_table(answer.result),
            "answer": answer.answer,
        })

    return Tool(
        name="query_loan_database",
        description=(
            "Answer a question about the fintech loan servicing database (borrowers, loans, "
            "payments, ledger) by generating and running a read-only SQL query."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to answer, in plain English.",
                }
            },
            "required": ["question"],
        },
        func=query_loan_database,
    )


def build_code_review_tool(provider, model: str) -> Tool:
    def review_pull_request(diff: str) -> str:
        return format_review(review_diff(diff, provider=provider, model=model))

    return Tool(
        name="review_pull_request",
        description="Review a unified diff and return structured code review feedback as markdown.",
        parameters={
            "type": "object",
            "properties": {
                "diff": {
                    "type": "string",
                    "description": "A unified diff (git diff output) to review.",
                }
            },
            "required": ["diff"],
        },
        func=review_pull_request,
    )


def build_default_registry(provider, model: str, connection_factory=None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(build_sql_tool(provider, model, connection_factory=connection_factory))
    registry.register(build_code_review_tool(provider, model))
    return registry
