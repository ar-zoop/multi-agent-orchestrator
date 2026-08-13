"""Routes a request to the provider that owns its model, with vendor failover.

`RoutingProvider` sits where `default_providers()` used to be dropped
straight into a `FallbackProvider`. For each request it:

1. Looks up which provider owns `request.model` (see `model_registry.py`).
2. Builds a provider order with that vendor first, the others after.
3. Wraps every non-primary provider so that, if the chain reaches it, the
   provider runs its *own* default model instead of the caller's original
   model id (a Claude model id means nothing to the OpenAI API).
4. Delegates the actual attempt/retry/circuit-breaker loop to the existing
   `FallbackProvider`, unchanged.

If the model isn't recognized at all, it falls back to the previous
behaviour: try every configured provider, in the order they were passed in,
with the literal requested model - so an unrecognized-but-valid id (a
model this table hasn't been updated for yet) still has a chance to work
against whichever vendor actually serves it.
"""

from orchestrator.providers.base import Provider
from orchestrator.providers.fallback_provider import FallbackProvider
from orchestrator.providers.model_registry import (
    UnknownModelError,
    default_model_for,
    provider_for_model,
)


class _ModelOverrideProvider(Provider):
    """Delegates to `provider`, substituting `model` for the request's model.

    Used for every non-primary provider in the routed order, so failing
    over to a different vendor means "do this with your own model," not
    "try to make sense of a model id that belongs to someone else."
    """

    def __init__(self, provider: Provider, model: str):
        self._provider = provider
        self._model = model

    @property
    def name(self) -> str:
        return self._provider.name

    def _with_model(self, request):
        return request.model_copy(update={"model": self._model})

    def complete(self, request):
        return self._provider.complete(self._with_model(request))

    def stream(self, request):
        return self._provider.stream(self._with_model(request))


class RoutingProvider(Provider):
    name = "routing"

    def __init__(self, providers: list[Provider], circuit_breaker,
                 max_retries_per_provider: int = 2, base_delay: float = 1.0):
        if not providers:
            raise ValueError("RoutingProvider requires at least one provider")
        self._providers_by_name = {p.name: p for p in providers}
        self._order = [p.name for p in providers]
        self.circuit_breaker = circuit_breaker
        self.max_retries_per_provider = max_retries_per_provider
        self.base_delay = base_delay

    def _ordered_providers(self, model: str) -> list[Provider]:
        try:
            primary = provider_for_model(model)
        except UnknownModelError:
            # Unrecognized model: preserve the old "try everyone, literal
            # model string" behaviour rather than guessing a vendor.
            return [self._providers_by_name[name] for name in self._order]

        names = [primary] + [n for n in self._order if n != primary]
        ordered = []
        for name in names:
            provider = self._providers_by_name.get(name)
            if provider is None:
                continue
            if name == primary:
                ordered.append(provider)
            else:
                ordered.append(_ModelOverrideProvider(provider, default_model_for(name)))
        return ordered

    def _chain_for(self, model: str) -> FallbackProvider:
        return FallbackProvider(
            providers=self._ordered_providers(model),
            circuit_breaker=self.circuit_breaker,
            max_retries_per_provider=self.max_retries_per_provider,
            base_delay=self.base_delay,
        )

    def complete(self, request):
        return self._chain_for(request.model).complete(request)

    def stream(self, request):
        return self._chain_for(request.model).stream(request)
