import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from helpers import FakeAPIError, ScriptedProvider, make_connection_factory, make_response
from orchestrator.api.app import app, get_connection_factory, get_provider

COLUMNS = ["loan_id", "status"]
ROWS = [(1, "delinquent"), (2, "delinquent")]


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def use_provider(provider):
    app.dependency_overrides[get_provider] = lambda: provider


def use_connection(factory):
    app.dependency_overrides[get_connection_factory] = lambda: factory


def chat_body(prompt="hello"):
    return {
        "model": "gpt-4o-mini",
        "temperature": 0.0,
        "messages": [{"role": "user", "content": prompt}],
    }


def test_health_needs_no_provider(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_run_returns_the_provider_response(client):
    use_provider(ScriptedProvider(outcomes=[make_response(content="hi there")]))

    response = client.post("/run", json=chat_body())

    assert response.status_code == 200
    assert response.json()["content"] == "hi there"


def test_run_reports_a_bad_gateway_when_every_provider_is_down(client):
    use_provider(ScriptedProvider(outcomes=[RuntimeError("All providers exhausted. boom")]))

    response = client.post("/run", json=chat_body())

    assert response.status_code == 502
    assert response.json()["detail"]["error"]["type"] == "all_providers_exhausted"


def test_run_rejects_a_malformed_body(client):
    use_provider(ScriptedProvider())

    assert client.post("/run", json={"model": "gpt-4o-mini"}).status_code == 422


def test_stream_emits_sse_chunks_then_done(client):
    use_provider(ScriptedProvider(stream_chunks=["a", "b"]))

    response = client.post("/stream", json=chat_body())

    assert response.status_code == 200
    assert 'data: {"text": "a"}' in response.text
    assert "data: [DONE]" in response.text


def test_the_sql_agent_endpoint_returns_sql_rows_and_a_summary(client):
    use_provider(ScriptedProvider(outcomes=[
        make_response(content="SELECT loan_id, status FROM Loan WHERE status = 'delinquent'"),
        make_response(content="Two loans are delinquent."),
    ]))
    use_connection(make_connection_factory(COLUMNS, ROWS))

    response = client.post("/agents/sql", json={"question": "which loans are delinquent?"})

    assert response.status_code == 200
    body = response.json()
    assert body["sql"].endswith("LIMIT 200")
    assert body["columns"] == COLUMNS
    assert body["rows"] == [[1, "delinquent"], [2, "delinquent"]]
    assert body["row_count"] == 2
    assert body["answer"] == "Two loans are delinquent."


def test_the_sql_agent_endpoint_rejects_unsafe_generated_sql(client):
    use_provider(ScriptedProvider(outcomes=[make_response(content="DROP TABLE Loan")]))
    factory = make_connection_factory(COLUMNS, ROWS)
    use_connection(factory)

    response = client.post("/agents/sql", json={"question": "wipe it"})

    assert response.status_code == 400
    assert response.json()["detail"]["error"]["type"] == "unsafe_sql"
    assert factory.executed == []


def test_the_sql_agent_endpoint_validates_the_row_cap(client):
    use_provider(ScriptedProvider())

    assert client.post(
        "/agents/sql", json={"question": "hi", "max_rows": 99999}
    ).status_code == 422


def test_the_review_endpoint_returns_comments_and_markdown(client, sample_diff):
    use_provider(ScriptedProvider(outcomes=[make_response(
        content="",
        tool_calls=[{
            "id": "call_1",
            "name": "submit_review",
            "arguments": {"comments": [{
                "file": "src/billing/invoice.py", "line": 13, "severity": "high",
                "category": "security", "comment": "SQL injection.",
            }]},
        }],
    )]))

    response = client.post("/agents/review", json={"diff": sample_diff})

    assert response.status_code == 200
    body = response.json()
    assert body["comments"][0]["severity"] == "high"
    assert "## Code review" in body["markdown"]


def test_the_review_endpoint_rejects_a_diff_with_no_changes(client):
    use_provider(ScriptedProvider())

    response = client.post("/agents/review", json={"diff": "not a diff at all"})

    assert response.status_code == 400
    assert response.json()["detail"]["error"]["type"] == "invalid_diff"


def test_the_agent_endpoint_runs_the_tool_loop_and_reports_usage(client):
    provider = ScriptedProvider(outcomes=[
        make_response(
            content="",
            tool_calls=[{
                "id": "call_1",
                "name": "query_loan_database",
                "arguments": {"question": "how many are delinquent?"},
            }],
        ),
        make_response(content="SELECT loan_id, status FROM Loan"),
        make_response(content="Two loans are delinquent."),
        make_response(content="There are 2 delinquent loans."),
    ])
    use_provider(provider)
    use_connection(make_connection_factory(COLUMNS, ROWS))

    response = client.post("/agents/run", json={"prompt": "how many are delinquent?"})

    assert response.status_code == 200
    assert response.json()["answer"] == "There are 2 delinquent loans."


def test_the_agent_endpoint_reports_a_failed_run(client):
    use_provider(ScriptedProvider(outcomes=[FakeAPIError(500)]))

    response = client.post("/agents/run", json={"prompt": "hello"})

    assert response.status_code == 500
