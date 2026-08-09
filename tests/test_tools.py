import json

from helpers import ScriptedProvider, make_connection_factory, make_response
from orchestrator.agents.tools import build_code_review_tool, build_default_registry, build_sql_tool
from orchestrator.core.agent import Agent

COLUMNS = ["loan_id", "status"]
ROWS = [(1, "delinquent"), (2, "delinquent")]


def test_the_sql_tool_exposes_a_question_parameter():
    tool = build_sql_tool(ScriptedProvider(), model="gpt-4o-mini")

    assert tool.name == "query_loan_database"
    assert tool.parameters["required"] == ["question"]


def test_calling_the_sql_tool_returns_the_sql_rows_and_answer():
    provider = ScriptedProvider(outcomes=[
        make_response(content="SELECT loan_id, status FROM Loan"),
        make_response(content="Two loans are delinquent."),
    ])
    factory = make_connection_factory(COLUMNS, ROWS)
    tool = build_sql_tool(provider, model="gpt-4o-mini", connection_factory=factory)

    payload = json.loads(tool.func(question="which loans are delinquent?"))

    assert payload["sql"] == "SELECT loan_id, status FROM Loan LIMIT 200"
    assert payload["row_count"] == 2
    assert payload["answer"] == "Two loans are delinquent."
    assert "loan_id | status" in payload["table"]


def test_the_code_review_tool_returns_markdown(sample_diff):
    provider = ScriptedProvider(outcomes=[make_response(
        content="",
        tool_calls=[{
            "id": "call_1",
            "name": "submit_review",
            "arguments": {"comments": [{
                "file": "src/billing/invoice.py", "line": 13, "severity": "high",
                "category": "security", "comment": "SQL injection.",
            }]},
        }],
    )])
    tool = build_code_review_tool(provider, model="gpt-4o-mini")

    markdown = tool.func(diff=sample_diff)

    assert "## Code review" in markdown
    assert "SQL injection." in markdown


def test_the_default_registry_holds_both_agents():
    registry = build_default_registry(ScriptedProvider(), model="gpt-4o-mini")

    assert sorted(registry.names()) == ["query_loan_database", "review_pull_request"]


def test_an_agent_can_answer_a_question_through_the_sql_tool():
    provider = ScriptedProvider(outcomes=[
        make_response(
            content="",
            tool_calls=[{
                "id": "call_1",
                "name": "query_loan_database",
                "arguments": {"question": "how many loans are delinquent?"},
            }],
        ),
        make_response(content="SELECT loan_id, status FROM Loan WHERE status = 'delinquent'"),
        make_response(content="Two loans are delinquent."),
        make_response(content="There are 2 delinquent loans."),
    ])
    factory = make_connection_factory(COLUMNS, ROWS)
    registry = build_default_registry(provider, model="gpt-4o-mini", connection_factory=factory)
    agent = Agent(provider=provider, model="gpt-4o-mini", tool_registry=registry)

    assert agent.run("how many loans are delinquent?") == "There are 2 delinquent loans."
    assert factory.executed == [
        "SELECT loan_id, status FROM Loan WHERE status = 'delinquent' LIMIT 200"
    ]


def test_a_rejected_query_surfaces_as_a_tool_error_not_a_crash():
    provider = ScriptedProvider(outcomes=[
        make_response(
            content="",
            tool_calls=[{
                "id": "call_1",
                "name": "query_loan_database",
                "arguments": {"question": "delete everything"},
            }],
        ),
        make_response(content="DROP TABLE Loan"),
        make_response(content="I cannot do that."),
    ])
    factory = make_connection_factory(COLUMNS, ROWS)
    registry = build_default_registry(provider, model="gpt-4o-mini", connection_factory=factory)
    agent = Agent(provider=provider, model="gpt-4o-mini", tool_registry=registry)

    assert agent.run("delete everything") == "I cannot do that."
    assert factory.executed == []
    assert "safety guard" in provider.requests[2].messages[-1].content
