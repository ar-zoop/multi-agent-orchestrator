"""Static mapping from a requested model id to the provider that serves it.

Before this module existed, the fallback chain just passed whatever `model`
string a caller sent straight to every provider in turn (see
`fallback_provider.py`) and let attempts against the wrong vendor 404 out.
That happened to work when a model id was obviously wrong for a given
vendor, but there was no real routing: a request for a Claude model still
hit OpenAI first, burning a retryable-looking round trip, and if a model id
wasn't recognized by *any* configured vendor the whole chain failed with
"all_providers_exhausted" even though the caller only ever wanted one
provider.

This module makes the model -> provider mapping explicit, and gives each
provider a default model to fall back to when the chain moves to it after
the originally requested model's own provider fails - so failover means
"ask a different vendor to do the same job," not "resend a model id that
vendor has never heard of."
"""

# Canonical model id -> provider name. Keep in sync with
# cost_tracker.PRICING: every model that can be routed here should have a
# price there, or CostTrackingProvider will log a warning and record $0.00.
MODEL_PROVIDER: dict[str, str] = {
    "gpt-4.1-nano": "openai",
    "gpt-4o-mini": "openai",
    "claude-haiku-4-5": "anthropic",
    "gemini-2.5-flash-lite": "google",
}

# Prefix fallback for model ids that aren't listed above yet - e.g. a caller
# passes a dated snapshot like "gpt-4o-mini-2024-07-18" or a model released
# after this table was last updated. First matching prefix wins, so list
# longer/more specific prefixes first within a vendor if that ever matters.
PROVIDER_PREFIXES: tuple[tuple[str, str], ...] = (
    ("gpt-", "openai"),
    ("o1-", "openai"),
    ("o3-", "openai"),
    ("chatgpt-", "openai"),
    ("claude-", "anthropic"),
    ("gemini-", "google"),
)

# What each provider runs when the chain fails over to it and the original
# model id isn't one of its own.
DEFAULT_MODEL_FOR_PROVIDER: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5",
    "google": "gemini-2.5-flash-lite",
}


class UnknownModelError(ValueError):
    def __init__(self, model: str):
        self.model = model
        super().__init__(
            f"Model '{model}' is not mapped to a provider. "
            f"Known models: {sorted(MODEL_PROVIDER)}"
        )


def provider_for_model(model: str) -> str:
    """Return the provider name that serves `model`.

    Raises UnknownModelError if `model` doesn't match a known id or a known
    vendor prefix - callers should treat that as "route to nothing in
    particular" rather than guessing.
    """
    if model in MODEL_PROVIDER:
        return MODEL_PROVIDER[model]
    for prefix, provider in PROVIDER_PREFIXES:
        if model.startswith(prefix):
            return provider
    raise UnknownModelError(model)


def default_model_for(provider_name: str) -> str:
    return DEFAULT_MODEL_FOR_PROVIDER[provider_name]
