import pytest

from helpers import ScriptedProvider, make_response
from orchestrator.core.chat_message import Message
from orchestrator.core.chat_request import ChatRequest
from orchestrator.core.cost_tracker import CostTrackingProvider
from orchestrator.core.spend_cap import SpendCapExceeded, SpendCapProvider

MODEL = "gpt-4o-mini"


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def request(prompt="hello"):
    return ChatRequest(
        messages=[Message(role="user", content=prompt)], model=MODEL, temperature=0.0
    )


def expensive_response():
    # gpt-4o-mini at $0.15/$0.60 per million: 1M in + 1M out = $0.75 a call.
    return make_response(input_tokens=1_000_000, output_tokens=1_000_000)


def test_calls_pass_through_while_there_is_budget_left():
    capped = SpendCapProvider(ScriptedProvider(), cap_usd=1.0)

    assert capped.complete(request()).content == "hello"
    assert capped.spent == pytest.approx(0.0000045)


def test_the_cap_stops_calls_once_the_budget_is_gone():
    inner = ScriptedProvider(outcomes=[expensive_response()])
    capped = SpendCapProvider(inner, cap_usd=0.5)

    capped.complete(request())

    with pytest.raises(SpendCapExceeded):
        capped.complete(request())
    assert inner.call_count == 1, "the provider must not be called once the cap is hit"


def test_the_budget_resets_when_the_window_rolls_over():
    clock = FakeClock()
    inner = ScriptedProvider(outcomes=[expensive_response()])
    capped = SpendCapProvider(inner, cap_usd=0.5, window_seconds=60.0, clock=clock)

    capped.complete(request())
    with pytest.raises(SpendCapExceeded):
        capped.complete(request())

    clock.advance(61)

    capped.complete(request())
    assert inner.call_count == 2


def test_streaming_is_charged_against_the_cap_too():
    capped = SpendCapProvider(ScriptedProvider(stream_chunks=["a" * 400]), cap_usd=1.0)

    assert list(capped.stream(request())) == ["a" * 400]
    assert capped.spent > 0, "streamed output must not be free"


def test_a_streaming_call_is_refused_when_the_cap_is_gone():
    inner = ScriptedProvider(outcomes=[expensive_response()], stream_chunks=["a"])
    capped = SpendCapProvider(inner, cap_usd=0.5)
    capped.complete(request())

    with pytest.raises(SpendCapExceeded):
        list(capped.stream(request()))


def test_an_unpriced_model_does_not_crash_the_cap():
    capped = SpendCapProvider(ScriptedProvider(), cap_usd=1.0)
    unpriced = ChatRequest(
        messages=[Message(role="user", content="hi")], model="some-new-model", temperature=0.0
    )

    capped.complete(unpriced)

    assert capped.spent == 0.0


def test_the_cap_can_be_disabled():
    inner = ScriptedProvider(outcomes=[expensive_response()])
    capped = SpendCapProvider(inner, cap_usd=None)

    for _ in range(3):
        capped.complete(request())

    assert inner.call_count == 3
    assert capped.remaining is None


def test_from_env_reads_the_cap(monkeypatch):
    monkeypatch.setenv("SPEND_CAP_USD", "2.50")
    monkeypatch.setenv("SPEND_CAP_WINDOW_SECONDS", "3600")

    capped = SpendCapProvider.from_env(ScriptedProvider())

    assert capped.cap_usd == 2.50
    assert capped.window_seconds == 3600.0


@pytest.mark.parametrize("value", ["0", "off", "none"])
def test_from_env_can_switch_the_cap_off(monkeypatch, value):
    monkeypatch.setenv("SPEND_CAP_USD", value)

    assert SpendCapProvider.from_env(ScriptedProvider()).cap_usd is None


def test_it_reports_the_wrapped_cost_trackers_usage():
    tracked = CostTrackingProvider(ScriptedProvider())
    capped = SpendCapProvider(tracked, cap_usd=1.0)

    capped.complete(request())

    assert capped.usage_by_provider["openai"].calls == 1
    assert capped.totals().calls == 1


def test_the_snapshot_describes_the_remaining_budget():
    capped = SpendCapProvider(ScriptedProvider(), cap_usd=1.0, window_seconds=60.0)

    snapshot = capped.snapshot()

    assert snapshot["cap_usd"] == 1.0
    assert snapshot["remaining_usd"] == 1.0
    assert snapshot["resets_in_seconds"] <= 60
