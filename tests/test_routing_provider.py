import pytest

from orchestrator.core.chat_request import ChatRequest
from orchestrator.core.chat_response import ChatResponse
from orchestrator.core.circuit_breaker import CircuitBreaker
from orchestrator.providers.base import Provider
from orchestrator.providers.routing_provider import RoutingProvider
from orchestrator.providers.model_registry import provider_for_model, UnknownModelError


def make_request(model: str) -> ChatRequest:
    return ChatRequest(messages=[], model=model, temperature=0.0)


class FakeProvider(Provider):
    def __init__(self, name: str, fail: bool = False):
        self.name = name
        self.fail = fail
        self.seen_models = []

    def complete(self, request):
        self.seen_models.append(request.model)
        if self.fail:
            err = Exception("boom")
            err.status_code = 401  # non-retryable, so fallback moves on immediately
            raise err
        return ChatResponse(
            content=f"hi from {self.name}",
            provider=self.name,
            input_tokens=1,
            output_tokens=1,
            stop_reason="final",
        )

    def stream(self, request):
        raise NotImplementedError


def make_breaker():
    return CircuitBreaker(failure_threshold=100, cooldown_seconds=30.0)


def test_model_registry_routes_known_models():
    assert provider_for_model("gpt-4o-mini") == "openai"
    assert provider_for_model("claude-haiku-4-5") == "anthropic"
    assert provider_for_model("gemini-2.5-flash-lite") == "google"


def test_model_registry_routes_unlisted_models_by_prefix():
    assert provider_for_model("gpt-4o-mini-2024-07-18") == "openai"
    assert provider_for_model("claude-3-5-sonnet-20241022") == "anthropic"
    assert provider_for_model("gemini-2.0-flash") == "google"


def test_model_registry_raises_for_unknown_model():
    with pytest.raises(UnknownModelError):
        provider_for_model("some-random-model")


def test_routes_claude_model_to_anthropic_first_without_touching_openai():
    openai = FakeProvider("openai")
    anthropic = FakeProvider("anthropic")
    google = FakeProvider("google")

    routing = RoutingProvider(
        providers=[openai, anthropic, google],
        circuit_breaker=make_breaker(),
        max_retries_per_provider=1,
        base_delay=0,
    )

    response = routing.complete(make_request("claude-haiku-4-5"))

    assert response.provider == "anthropic"
    assert openai.seen_models == []
    assert anthropic.seen_models == ["claude-haiku-4-5"]
    assert google.seen_models == []


def test_routes_gpt_model_to_openai_first():
    openai = FakeProvider("openai")
    anthropic = FakeProvider("anthropic")
    google = FakeProvider("google")

    routing = RoutingProvider(
        providers=[openai, anthropic, google],
        circuit_breaker=make_breaker(),
        max_retries_per_provider=1,
        base_delay=0,
    )

    response = routing.complete(make_request("gpt-4o-mini"))

    assert response.provider == "openai"
    assert openai.seen_models == ["gpt-4o-mini"]
    assert anthropic.seen_models == []


def test_fails_over_to_next_vendor_using_that_vendors_own_default_model():
    openai = FakeProvider("openai", fail=True)
    anthropic = FakeProvider("anthropic")
    google = FakeProvider("google")

    routing = RoutingProvider(
        providers=[openai, anthropic, google],
        circuit_breaker=make_breaker(),
        max_retries_per_provider=1,
        base_delay=0,
    )

    response = routing.complete(make_request("gpt-4o-mini"))

    assert response.provider == "anthropic"
    assert openai.seen_models == ["gpt-4o-mini"]
    # Anthropic never sees the OpenAI model id - it runs its own default.
    assert anthropic.seen_models == ["claude-haiku-4-5"]


def test_unknown_model_falls_back_to_trying_every_provider_with_literal_model():
    openai = FakeProvider("openai", fail=True)
    anthropic = FakeProvider("anthropic")

    routing = RoutingProvider(
        providers=[openai, anthropic],
        circuit_breaker=make_breaker(),
        max_retries_per_provider=1,
        base_delay=0,
    )

    response = routing.complete(make_request("some-future-model"))

    assert response.provider == "anthropic"
    assert openai.seen_models == ["some-future-model"]
    assert anthropic.seen_models == ["some-future-model"]
