import logging

import pytest

from orchestrator.core.cost_tracker import PRICING, CostTrackingProvider, estimate_cost
from helpers import ScriptedProvider, make_response


class Request:
    def __init__(self, model):
        self.model = model


def test_estimate_cost_uses_the_pricing_table():
    input_price, output_price = PRICING["gpt-4o-mini"]
    assert estimate_cost("gpt-4o-mini", 1_000_000, 0) == pytest.approx(input_price)
    assert estimate_cost("gpt-4o-mini", 0, 1_000_000) == pytest.approx(output_price)
    assert estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000) == pytest.approx(
        input_price + output_price
    )


def test_estimate_cost_is_zero_for_zero_tokens():
    assert estimate_cost("gpt-4o-mini", 0, 0) == 0.0


def test_estimate_cost_rejects_unknown_models():
    with pytest.raises(ValueError, match="not found in pricing table"):
        estimate_cost("some-model-we-never-priced", 100, 100)


def test_complete_returns_the_wrapped_response_unchanged():
    inner = ScriptedProvider(outcomes=[make_response("openai", content="hi")])
    tracker = CostTrackingProvider(inner)

    response = tracker.complete(Request("gpt-4o-mini"))

    assert response.content == "hi"
    assert response.provider == "openai"
    assert inner.call_count == 1


def test_usage_accumulates_across_calls_for_the_same_provider():
    inner = ScriptedProvider(
        outcomes=[make_response("openai", input_tokens=1000, output_tokens=500)]
    )
    tracker = CostTrackingProvider(inner)

    tracker.complete(Request("gpt-4o-mini"))
    tracker.complete(Request("gpt-4o-mini"))

    stats = tracker.usage_by_provider["openai"]
    assert stats.calls == 2
    assert stats.input_tokens == 2000
    assert stats.output_tokens == 1000
    assert stats.cost == pytest.approx(2 * estimate_cost("gpt-4o-mini", 1000, 500))


def test_usage_is_bucketed_per_provider():
    inner = ScriptedProvider(
        outcomes=[
            make_response("openai", input_tokens=100, output_tokens=10),
            make_response("anthropic", input_tokens=200, output_tokens=20),
        ]
    )
    tracker = CostTrackingProvider(inner)

    tracker.complete(Request("gpt-4o-mini"))
    tracker.complete(Request("claude-haiku-4-5"))

    assert set(tracker.usage_by_provider) == {"openai", "anthropic"}
    assert tracker.usage_by_provider["openai"].input_tokens == 100
    assert tracker.usage_by_provider["anthropic"].input_tokens == 200


def test_unknown_model_records_zero_cost_but_still_counts_tokens(caplog):
    inner = ScriptedProvider(
        outcomes=[make_response("openai", input_tokens=100, output_tokens=10)]
    )
    tracker = CostTrackingProvider(inner)

    with caplog.at_level(logging.WARNING):
        tracker.complete(Request("brand-new-unpriced-model"))

    stats = tracker.usage_by_provider["openai"]
    assert stats.cost == 0.0
    assert stats.calls == 1
    assert stats.input_tokens == 100
    assert "No pricing entry" in caplog.text


def test_totals_sums_every_provider_bucket():
    inner = ScriptedProvider(
        outcomes=[
            make_response("openai", input_tokens=100, output_tokens=10),
            make_response("anthropic", input_tokens=200, output_tokens=20),
        ]
    )
    tracker = CostTrackingProvider(inner)

    tracker.complete(Request("gpt-4o-mini"))
    tracker.complete(Request("claude-haiku-4-5"))

    totals = tracker.totals()
    assert totals.calls == 2
    assert totals.input_tokens == 300
    assert totals.output_tokens == 30
    assert totals.cost == pytest.approx(
        estimate_cost("gpt-4o-mini", 100, 10) + estimate_cost("claude-haiku-4-5", 200, 20)
    )


def test_reset_clears_usage():
    inner = ScriptedProvider(outcomes=[make_response("openai")])
    tracker = CostTrackingProvider(inner)
    tracker.complete(Request("gpt-4o-mini"))

    tracker.reset()

    assert tracker.usage_by_provider == {}
    assert tracker.totals().calls == 0


def test_stream_passes_chunks_through_untouched():
    inner = ScriptedProvider(stream_chunks=["a", "b", "c"])
    tracker = CostTrackingProvider(inner)

    assert list(tracker.stream(Request("gpt-4o-mini"))) == ["a", "b", "c"]


def test_stream_logs_latency_even_when_the_provider_blows_up(caplog):
    inner = ScriptedProvider(stream_chunks=["a", RuntimeError("boom")])
    tracker = CostTrackingProvider(inner)

    with caplog.at_level(logging.INFO):
        with pytest.raises(RuntimeError, match="boom"):
            list(tracker.stream(Request("gpt-4o-mini")))

    assert "streaming cost not tracked" in caplog.text


def test_inner_name_exposes_the_wrapped_provider_name():
    tracker = CostTrackingProvider(ScriptedProvider(name="anthropic"))
    assert tracker.inner_name == "anthropic"
