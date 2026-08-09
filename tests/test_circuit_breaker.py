from orchestrator.core.circuit_breaker import CircuitBreaker


def test_a_fresh_breaker_is_closed():
    assert CircuitBreaker().is_open("openai") is False


def test_it_stays_closed_below_the_failure_threshold():
    breaker = CircuitBreaker(failure_threshold=3)
    breaker.record_failure("openai")
    breaker.record_failure("openai")

    assert breaker.is_open("openai") is False
    assert breaker.failure_count("openai") == 2


def test_it_opens_once_the_threshold_is_reached():
    breaker = CircuitBreaker(failure_threshold=3)
    for _ in range(3):
        breaker.record_failure("openai")

    assert breaker.is_open("openai") is True


def test_opening_one_provider_does_not_affect_another():
    breaker = CircuitBreaker(failure_threshold=1)
    breaker.record_failure("openai")

    assert breaker.is_open("openai") is True
    assert breaker.is_open("anthropic") is False


def test_a_success_closes_the_circuit_and_clears_the_failure_count():
    breaker = CircuitBreaker(failure_threshold=2)
    breaker.record_failure("openai")
    breaker.record_failure("openai")
    assert breaker.is_open("openai") is True

    breaker.record_success("openai")

    assert breaker.is_open("openai") is False
    assert breaker.failure_count("openai") == 0


def test_the_circuit_closes_again_after_the_cooldown_elapses():
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=0)
    breaker.record_failure("openai")

    assert breaker.is_open("openai") is False
    assert breaker.failure_count("openai") == 0


def test_a_reopened_provider_needs_the_full_threshold_again(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(
        "orchestrator.core.circuit_breaker.time.monotonic", lambda: clock["now"]
    )
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=30)

    breaker.record_failure("openai")
    breaker.record_failure("openai")
    assert breaker.is_open("openai") is True

    clock["now"] += 31
    assert breaker.is_open("openai") is False

    breaker.record_failure("openai")
    assert breaker.is_open("openai") is False

    breaker.record_failure("openai")
    assert breaker.is_open("openai") is True


def test_it_stays_open_for_the_whole_cooldown(monkeypatch):
    clock = {"now": 500.0}
    monkeypatch.setattr(
        "orchestrator.core.circuit_breaker.time.monotonic", lambda: clock["now"]
    )
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=30)
    breaker.record_failure("openai")

    clock["now"] += 29
    assert breaker.is_open("openai") is True
