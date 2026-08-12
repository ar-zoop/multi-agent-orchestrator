import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from helpers import ScriptedProvider, make_response
from orchestrator.api.app import app, get_provider, get_rate_limiter
from orchestrator.api.rate_limit import RateLimiter, is_metered
from orchestrator.core.spend_cap import SpendCapProvider


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def chat_body(prompt="hello"):
    return {
        "model": "gpt-4o-mini",
        "temperature": 0.0,
        "messages": [{"role": "user", "content": prompt}],
    }


# -- the limiter itself ----------------------------------------------------


def test_it_allows_requests_up_to_the_limit():
    limiter = RateLimiter(max_requests=3, window_seconds=60.0, clock=FakeClock())

    assert [limiter.check("1.2.3.4") for _ in range(3)] == [None, None, None]


def test_it_blocks_the_request_after_the_limit_and_says_how_long_to_wait():
    clock = FakeClock()
    limiter = RateLimiter(max_requests=2, window_seconds=60.0, clock=clock)
    limiter.check("1.2.3.4")
    clock.advance(10)
    limiter.check("1.2.3.4")

    retry_after = limiter.check("1.2.3.4")

    assert retry_after == pytest.approx(50.0)


def test_the_window_slides_rather_than_resetting_in_blocks():
    clock = FakeClock()
    limiter = RateLimiter(max_requests=1, window_seconds=60.0, clock=clock)
    limiter.check("1.2.3.4")

    clock.advance(61)

    assert limiter.check("1.2.3.4") is None


def test_clients_are_limited_independently():
    limiter = RateLimiter(max_requests=1, window_seconds=60.0, clock=FakeClock())
    limiter.check("1.2.3.4")

    assert limiter.check("5.6.7.8") is None


def test_blocked_requests_do_not_extend_the_block():
    clock = FakeClock()
    limiter = RateLimiter(max_requests=1, window_seconds=60.0, clock=clock)
    limiter.check("1.2.3.4")

    for _ in range(5):
        limiter.check("1.2.3.4")
    clock.advance(61)

    assert limiter.check("1.2.3.4") is None


def test_only_the_endpoints_that_spend_money_are_metered():
    assert is_metered("/run")
    assert is_metered("/agents/sql")
    assert not is_metered("/health")
    assert not is_metered("/docs")


# -- the middleware --------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    limiter = RateLimiter(max_requests=2, window_seconds=60.0, clock=FakeClock())
    app.dependency_overrides[get_provider] = lambda: ScriptedProvider(
        outcomes=[make_response(content="hi there")]
    )
    monkeypatch.setattr("orchestrator.api.app._rate_limiter", limiter)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_the_health_check_is_never_rate_limited(client):
    for _ in range(5):
        assert client.get("/health").status_code == 200


def test_it_returns_429_with_a_retry_after_once_the_limit_is_hit(client):
    for _ in range(2):
        assert client.post("/run", json=chat_body()).status_code == 200

    response = client.post("/run", json=chat_body())

    assert response.status_code == 429
    assert response.json()["detail"]["error"]["type"] == "rate_limited"
    assert "retry-after" in response.headers


def test_allowed_responses_carry_the_remaining_budget(client):
    response = client.post("/run", json=chat_body())

    assert response.headers["x-ratelimit-limit"] == "2"
    assert response.headers["x-ratelimit-remaining"] == "1"


def test_forwarded_clients_are_limited_separately(client):
    for _ in range(2):
        client.post("/run", json=chat_body(), headers={"X-Forwarded-For": "9.9.9.9"})

    blocked = client.post("/run", json=chat_body(), headers={"X-Forwarded-For": "9.9.9.9"})
    other = client.post("/run", json=chat_body(), headers={"X-Forwarded-For": "8.8.8.8"})

    assert blocked.status_code == 429
    assert other.status_code == 200


def test_an_api_key_is_required_when_one_is_configured(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "secret")

    assert client.post("/run", json=chat_body()).status_code == 401
    assert client.post(
        "/run", json=chat_body(), headers={"X-API-Key": "secret"}
    ).status_code == 200


def test_the_limits_endpoint_reports_the_public_budget(client):
    app.dependency_overrides[get_provider] = lambda: SpendCapProvider(
        ScriptedProvider(), cap_usd=5.0
    )

    body = client.get("/limits").json()

    assert body["rate_limit"] == {"requests": 2, "window_seconds": 60}
    assert body["spend_cap"]["cap_usd"] == 5.0
    assert body["auth_required"] is False


def test_the_spend_cap_surfaces_as_402_on_run(client):
    capped = SpendCapProvider(
        ScriptedProvider(outcomes=[make_response(input_tokens=1_000_000, output_tokens=1_000_000)]),
        cap_usd=0.5,
    )
    app.dependency_overrides[get_provider] = lambda: capped
    client.post("/run", json=chat_body())

    response = client.post("/run", json=chat_body())

    assert response.status_code == 402
    assert response.json()["detail"]["error"]["type"] == "spend_cap_exceeded"
    assert response.headers["retry-after"]


def test_the_rate_limiter_dependency_is_the_configured_one(client):
    assert get_rate_limiter().max_requests == 2
