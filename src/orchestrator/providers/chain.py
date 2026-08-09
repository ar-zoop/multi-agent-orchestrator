from orchestrator.core.circuit_breaker import CircuitBreaker
from orchestrator.core.cost_tracker import CostTrackingProvider
from orchestrator.providers.base import Provider
from orchestrator.providers.fallback_provider import FallbackProvider


def build_provider_chain(
    providers: list[Provider],
    circuit_breaker: CircuitBreaker | None = None,
    max_retries_per_provider: int = 2,
    base_delay: float = 1.0,
    track_cost: bool = True,
) -> Provider:
    providers = list(providers)
    if not providers:
        raise ValueError("build_provider_chain requires at least one provider")
    chain = FallbackProvider(
        providers=providers,
        circuit_breaker=circuit_breaker or CircuitBreaker(),
        max_retries_per_provider=max_retries_per_provider,
        base_delay=base_delay,
    )
    if track_cost:
        return CostTrackingProvider(chain)
    return chain


def default_providers() -> list[Provider]:
    from orchestrator.providers.anthropic_provider import AnthropicProvider
    from orchestrator.providers.google_provider import GoogleProvider
    from orchestrator.providers.openai_provider import OpenAIProvider

    return [OpenAIProvider(), AnthropicProvider(), GoogleProvider()]
