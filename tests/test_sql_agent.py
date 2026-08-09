from datetime import date
from decimal import Decimal

import pytest

from helpers import ScriptedProvider, make_connection_factory, make_response
from orchestrator.agents.sql_agent import (
    SqlAgentError,
    SqlResult,
    answer_question,
    build_answer_request,
    build_sql_request,
    execute_sql,
    generate_sql,
    render_table,
)

COLUMNS = ["loan_id", "status", "loan_amount"]
ROWS = [(1, "delinquent", Decimal("250000.00")), (2, "active", Decimal("310500.50"))]


def test_the_schema_is_embedded_in_the_system_prompt():
    request = build_sql_request("how many loans?", model="gpt-4o-mini")

    system = request.messages[0].content
    assert "CREATE TABLE Loan" in system
    assert "Only ever write SELECT statements" in system
    assert request.messages[1].content == "how many loans?"
    assert request.temperature == 0.0


def test_generate_sql_strips_markdown_fences():
    provider = ScriptedProvider(
        outcomes=[make_response(content="```sql\nSELECT 1 FROM Loan\n```")]
    )

    assert generate_sql("q", provider, model="gpt-4o-mini") == "SELECT 1 FROM Loan"


def test_generate_sql_handles_a_plain_response():
    provider = ScriptedProvider(outcomes=[make_response(content="  SELECT 1  ")])

    assert generate_sql("q", provider, model="gpt-4o-mini") == "SELECT 1"


def test_execute_sql_runs_the_query_and_returns_rows():
    factory = make_connection_factory(COLUMNS, ROWS)

    result = execute_sql("SELECT loan_id, status, loan_amount FROM Loan", factory)

    assert result.columns == COLUMNS
    assert result.row_count == 2
    assert result.truncated is False
    assert factory.executed == ["SELECT loan_id, status, loan_amount FROM Loan LIMIT 200"]


def test_execute_sql_applies_a_row_cap_and_reports_truncation():
    rows = [(i, "active", Decimal("1")) for i in range(10)]
    factory = make_connection_factory(COLUMNS, rows)

    result = execute_sql("SELECT * FROM Loan", factory, max_rows=3)

    assert result.row_count == 3
    assert result.truncated is True
    assert factory.executed == ["SELECT * FROM Loan LIMIT 3"]


def test_execute_sql_does_not_double_up_an_existing_limit():
    factory = make_connection_factory(COLUMNS, ROWS)

    execute_sql("SELECT * FROM Loan LIMIT 2", factory, max_rows=100)

    assert factory.executed == ["SELECT * FROM Loan LIMIT 2"]


def test_execute_sql_refuses_to_run_a_destructive_statement():
    factory = make_connection_factory(COLUMNS, ROWS)

    with pytest.raises(Exception):
        execute_sql("DROP TABLE Loan", factory)

    assert factory.executed == []


def test_render_table_formats_decimals_and_dates_readably():
    result = SqlResult(
        sql="SELECT 1",
        columns=["loan_id", "origination_date", "amount", "note"],
        rows=[(1, date(2024, 3, 1), Decimal("1000.50"), None)],
        row_count=1,
    )

    table = render_table(result)

    assert "loan_id | origination_date | amount | note" in table
    assert "1 | 2024-03-01 | 1000.50 | NULL" in table


def test_render_table_says_so_when_there_are_no_rows():
    result = SqlResult(sql="SELECT 1", columns=["loan_id"], rows=[], row_count=0)

    assert "(no rows)" in render_table(result)


def test_render_table_caps_how_many_rows_the_model_sees():
    rows = [(i,) for i in range(10)]
    result = SqlResult(sql="SELECT 1", columns=["n"], rows=rows, row_count=10)

    table = render_table(result, max_rows=3)

    assert "5 more row(s) not shown" not in table
    assert "7 more row(s) not shown" in table


def test_the_answer_prompt_carries_the_question_sql_and_results():
    result = SqlResult(sql="SELECT 1", columns=["n"], rows=[(1,)], row_count=1)

    request = build_answer_request("how many?", result, model="gpt-4o-mini")

    prompt = request.messages[1].content
    assert "how many?" in prompt
    assert "SELECT 1" in prompt
    assert "1 row(s)" in prompt


def test_answer_question_generates_executes_and_summarises():
    provider = ScriptedProvider(outcomes=[
        make_response(content="SELECT loan_id FROM Loan WHERE status = 'delinquent'"),
        make_response(content="There are 2 delinquent loans."),
    ])
    factory = make_connection_factory(COLUMNS, ROWS)

    answer = answer_question(
        "how many loans are delinquent?", provider, model="gpt-4o-mini", connection_factory=factory
    )

    assert answer.sql == "SELECT loan_id FROM Loan WHERE status = 'delinquent' LIMIT 200"
    assert answer.result.row_count == 2
    assert answer.answer == "There are 2 delinquent loans."
    assert provider.call_count == 2


def test_answer_question_rejects_unsafe_generated_sql_before_touching_the_database():
    provider = ScriptedProvider(outcomes=[make_response(content="DROP TABLE Loan")])
    factory = make_connection_factory(COLUMNS, ROWS)

    with pytest.raises(SqlAgentError, match="rejected by the safety guard"):
        answer_question("wipe it", provider, model="gpt-4o-mini", connection_factory=factory)

    assert factory.executed == []
    assert provider.call_count == 1


def test_answer_question_rejects_a_smuggled_second_statement():
    provider = ScriptedProvider(
        outcomes=[make_response(content="SELECT 1 FROM Loan; DELETE FROM Loan")]
    )
    factory = make_connection_factory(COLUMNS, ROWS)

    with pytest.raises(SqlAgentError):
        answer_question("be sneaky", provider, model="gpt-4o-mini", connection_factory=factory)

    assert factory.executed == []
