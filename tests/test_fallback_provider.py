import itertools

import pytest

from orchestrator.providers.base import Provider
from orchestrator.core.circuit_breaker import CircuitBreaker
from orchestrator.providers.fallback_provider import FallbackProvider, is_retryable
from orchestrator.core.chat_response import ChatResponse


class FakeAPIError(Exception):
    def __init__(self, status_code):
        super().__init__(f"fake error {status_code}")
        self.status_code = status_code


class FakeConnectionError(Exception):
    pass


def make_response(provider_name: str) -> ChatResponse:
    return ChatResponse(
        content=f"hello from {provider_name}",
        provider=provider_name,
        input_tokens=10,
        output_tokens=5,
        stop_reason="final",
    )


class FakeProvider(Provider):
    def __init__(self, name: str, outcomes: list):
        self.name = name
        self.call_count = 0
        last = outcomes[-1] if outcomes else None
        self._outcomes = itertools.chain(outcomes, itertools.repeat(last))

    def complete(self, request):
        self.call_count += 1
        outcome = next(self._outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def stream(self, request):
        raise NotImplementedError


def make_breaker(failure_threshold=3, cooldown_seconds=30.0):
    return CircuitBreaker(failure_threshold=failure_threshold, cooldown_seconds=cooldown_seconds)


def test_is_retryable_true_for_retryable_status_codes():
    assert is_retryable(FakeAPIError(429)) is True
    assert is_retryable(FakeAPIError(500)) is True
    assert is_retryable(FakeAPIError(503)) is True


def test_is_retryable_false_for_auth_and_bad_request():
    assert is_retryable(FakeAPIError(401)) is False
    assert is_retryable(FakeAPIError(400)) is False


def test_is_retryable_true_when_status_code_missing():
    assert is_retryable(FakeConnectionError("connection reset")) is True


def test_returns_first_provider_response_when_it_succeeds():
    openai = FakeProvider("openai", [make_response("openai")])
    anthropic = FakeProvider("anthropic", [make_response("anthropic")])

    fallback = FallbackProvider(
        providers=[openai, anthropic],
        circuit_breaker=make_breaker(),
        max_retries_per_provider=2,
        base_delay=0,
    )

    response = fallback.complete(request=None)

    assert response.provider == "openai"
    assert openai.call_count == 1
    assert anthropic.call_count == 0


def test_non_retryable_error_falls_back_without_retrying_same_provider():
    openai = FakeProvider("openai", [FakeAPIError(401)])
    anthropic = FakeProvider("anthropic", [make_response("anthropic")])

    fallback = FallbackProvider(
        providers=[openai, anthropic],
        circuit_breaker=make_breaker(),
        max_retries_per_provider=3,
        base_delay=0,
    )

    response = fallback.complete(request=None)

    assert response.provider == "anthropic"
    assert openai.call_count == 1
    assert anthropic.call_count == 1


def test_retryable_error_retries_same_provider_before_falling_back():
    openai = FakeProvider("openai", [FakeAPIError(429), FakeAPIError(429)])
    anthropic = FakeProvider("anthropic", [make_response("anthropic")])

    fallback = FallbackProvider(
        providers=[openai, anthropic],
        circuit_breaker=make_breaker(),
        max_retries_per_provider=2,
        base_delay=0,
    )

    response = fallback.complete(request=None)

    assert response.provider == "anthropic"
    assert openai.call_count == 2
    assert anthropic.call_count == 1


def test_retryable_error_that_recovers_mid_retry_succeeds_on_same_provider():
    openai = FakeProvider("openai", [FakeAPIError(429), make_response("openai")])
    anthropic = FakeProvider("anthropic", [make_response("anthropic")])

    fallback = FallbackProvider(
        providers=[openai, anthropic],
        circuit_breaker=make_breaker(),
        max_retries_per_provider=2,
        base_delay=0,
    )

    response = fallback.complete(request=None)

    assert response.provider == "openai"
    assert openai.call_count == 2
    assert anthropic.call_count == 0


def test_circuit_breaker_opens_after_repeated_failed_requests():
    openai = FakeProvider("openai", [FakeAPIError(401)])
    anthropic = FakeProvider("anthropic", [make_response("anthropic")])

    breaker = make_breaker(failure_threshold=3)
    fallback = FallbackProvider(
        providers=[openai, anthropic],
        circuit_breaker=breaker,
        max_retries_per_provider=1,
        base_delay=0,
    )

    fallback.complete(request=None)
    fallback.complete(request=None)
    fallback.complete(request=None)
    assert openai.call_count == 3
    assert breaker.is_open("openai") is True

    fallback.complete(request=None)
    assert openai.call_count == 3
    assert anthropic.call_count == 4


def test_raises_when_every_provider_is_exhausted():
    openai = FakeProvider("openai", [FakeAPIError(401)])
    anthropic = FakeProvider("anthropic", [FakeAPIError(500)])

    fallback = FallbackProvider(
        providers=[openai, anthropic],
        circuit_breaker=make_breaker(),
        max_retries_per_provider=1,
        base_delay=0,
    )

    with pytest.raises(RuntimeError, match="All providers exhausted"):
        fallback.complete(request=None)
