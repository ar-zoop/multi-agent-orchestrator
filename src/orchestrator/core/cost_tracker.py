import logging
import time

from orchestrator.core.usage_stats import UsageStats
from orchestrator.providers.base import Provider

logger = logging.getLogger(__name__)

PRICING = {
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-haiku-4-5": (1.00, 5.00),
    "gemini-2.5-flash-lite": (0.10, 0.40),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    if model not in PRICING:
        raise ValueError(f"Model {model} not found in pricing table.")
    input_price, output_price = PRICING[model]
    return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price


class CostTrackingProvider(Provider):
    name = "cost_tracking"

    def __init__(self, provider: Provider):
        self.provider = provider
        self.usage_by_provider: dict[str, UsageStats] = {}

    @property
    def inner_name(self) -> str:
        return getattr(self.provider, "name", "unknown")

    def complete(self, request):
        start = time.monotonic()
        response = self.provider.complete(request)
        latency = time.monotonic() - start
        try:
            cost = estimate_cost(request.model, response.input_tokens, response.output_tokens)
        except ValueError:
            logger.warning("No pricing entry for model %s - recording cost as 0.0", request.model)
            cost = 0.0
        stats = self.usage_by_provider.setdefault(response.provider, UsageStats())
        stats.cost += cost
        stats.input_tokens += response.input_tokens
        stats.output_tokens += response.output_tokens
        stats.calls += 1
        logger.info(
            "provider=%s model=%s input_tokens=%d output_tokens=%d latency=%.3fs cost=$%.6f",
            response.provider,
            request.model,
            response.input_tokens,
            response.output_tokens,
            latency,
            cost,
        )
        return response

    def stream(self, request):
        start = time.monotonic()
        try:
            yield from self.provider.stream(request)
        finally:
            latency = time.monotonic() - start
            logger.info(
                "provider=%s model=%s latency=%.3fs streaming cost not tracked",
                self.inner_name,
                request.model,
                latency,
            )

    def totals(self) -> UsageStats:
        total = UsageStats()
        for stats in self.usage_by_provider.values():
            total.cost += stats.cost
            total.input_tokens += stats.input_tokens
            total.output_tokens += stats.output_tokens
            total.calls += stats.calls
        return total

    def reset(self) -> None:
        self.usage_by_provider = {}
