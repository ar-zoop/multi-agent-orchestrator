import time
import logging

from orchestrator.providers.base import Provider
from orchestrator.core.usage_stats import UsageStats

logger = logging.getLogger(__name__)

# Format: {model_name: (input_price_per_million, output_price_per_million)}
PRICING = {
    "gpt-4.1-nano": (0.10, 0.40),
    "claude-haiku-4-5": (1.00, 5.00),
    "gemini-2.5-flash-lite": (0.10, 0.40),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    if model not in PRICING:
        raise ValueError(f"Model {model} not found in pricing table.")
    input_price, output_price = PRICING[model]
    cost = (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
    return cost
    


class CostTrackingProvider(Provider):
    def __init__(self, provider: Provider):
        self.provider = provider
        self.usage_by_provider: dict[str, UsageStats] = {}

    def complete(self, request):
        start = time.monotonic()
        response = self.provider.complete(request)
        latency = time.monotonic() - start
        try:
            cost = estimate_cost(request.model, response.input_tokens, response.output_tokens)
        except Exception as e:
            print("Error:", e)
            cost = 0.0
        stats = self.usage_by_provider.setdefault(response.provider, UsageStats())
        stats.cost += cost
        stats.input_tokens += response.input_tokens
        stats.output_tokens += response.output_tokens
        stats.calls += 1

        logger.info("Provider: %s, Model: %s, Input Tokens: %d, Output Tokens: %d, Latency: %.2f seconds, Cost: $%.6f", response.provider, request.model, response.input_tokens, response.output_tokens, latency, cost)
        return response

    def stream(self, request):
        # NOTE: streaming chunks are plain text deltas with no per-chunk usage
        # data, so we can't compute cost here the way complete() does. Only
        # latency is tracked for now - revisit if the provider stream shape
        # ever exposes a final usage event we can hook into.
        start = time.monotonic()
        try:
            yield from self.provider.stream(request)
        finally:
            latency = time.monotonic() - start
            logger.info("Provider: %s, Model: %s, Latency: %.2f seconds (streaming - cost not tracked)", self.provider.name, request.model, latency)
