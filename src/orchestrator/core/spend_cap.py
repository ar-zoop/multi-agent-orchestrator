"""A hard ceiling on what the public demo is allowed to spend.

The orchestrator is deployed on a public URL with no authentication, so anything
that reaches a provider is spending real credits. `CostTrackingProvider` already
knows what every call costs; this wrapper turns that number into a budget and
refuses the call once the budget is gone.

It is a `Provider` like everything else in the chain, so it composes:

    SpendCapProvider -> CostTrackingProvider -> FallbackProvider -> vendor SDK
"""

import logging
import os
import threading
import time

from orchestrator.core.cost_tracker import estimate_cost
from orchestrator.core.usage_stats import UsageStats
from orchestrator.providers.base import Provider

logger = logging.getLogger(__name__)

DEFAULT_CAP_USD = 5.0
DEFAULT_WINDOW_SECONDS = 86_400.0

# Streaming responses do not report token counts, so streamed spend is estimated
# from character counts. Four characters per token is the usual rule of thumb.
CHARS_PER_TOKEN = 4


class SpendCapExceeded(RuntimeError):
    """Raised instead of calling a provider once the budget for the window is gone."""

    status_code = 402

    def __init__(self, spent: float, cap: float, resets_in: float):
        self.spent = spent
        self.cap = cap
        self.resets_in = resets_in
        super().__init__(
            f"Demo spend cap reached: ${spent:.4f} of ${cap:.2f} used. "
            f"Budget resets in {int(resets_in)}s."
        )


def _tokens_from_chars(chars: int) -> int:
    return max(1, chars // CHARS_PER_TOKEN)


class SpendCapProvider(Provider):
    """Refuses to spend more than `cap_usd` per rolling window.

    The counter is in-process and resets on redeploy, which is the right trade-off
    for a single-instance demo: no external state, and a restart can only ever
    reset a budget that was already capped.
    """

    name = "spend_cap"

    def __init__(
        self,
        provider: Provider,
        cap_usd: float | None = DEFAULT_CAP_USD,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        clock=time.monotonic,
    ):
        self.provider = provider
        self.cap_usd = cap_usd
        self.window_seconds = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._spent = 0.0
        self._window_start = clock()

    @classmethod
    def from_env(cls, provider: Provider, **kwargs) -> "SpendCapProvider":
        """`SPEND_CAP_USD=0` (or `off`) disables the cap; unset uses the default."""
        raw = os.getenv("SPEND_CAP_USD", "").strip()
        if raw.lower() in {"off", "none", "disabled"}:
            cap = None
        elif raw:
            cap = float(raw)
            if cap <= 0:
                cap = None
        else:
            cap = DEFAULT_CAP_USD

        window = float(os.getenv("SPEND_CAP_WINDOW_SECONDS", DEFAULT_WINDOW_SECONDS))
        return cls(provider, cap_usd=cap, window_seconds=window, **kwargs)

    # -- budget bookkeeping -------------------------------------------------

    def _roll_window(self) -> None:
        now = self._clock()
        if now - self._window_start >= self.window_seconds:
            self._window_start = now
            self._spent = 0.0

    def _check(self) -> None:
        if self.cap_usd is None:
            return
        with self._lock:
            self._roll_window()
            if self._spent >= self.cap_usd:
                resets_in = self.window_seconds - (self._clock() - self._window_start)
                logger.warning(
                    "spend cap reached: $%.4f of $%.2f, resets in %ds",
                    self._spent,
                    self.cap_usd,
                    int(resets_in),
                )
                raise SpendCapExceeded(self._spent, self.cap_usd, max(0.0, resets_in))

    def _charge(self, model: str, input_tokens: int, output_tokens: int) -> float:
        try:
            cost = estimate_cost(model, input_tokens, output_tokens)
        except ValueError:
            logger.warning("No pricing entry for model %s - charging $0.00 to the cap", model)
            cost = 0.0
        with self._lock:
            self._roll_window()
            self._spent += cost
        return cost

    # -- Provider -----------------------------------------------------------

    def complete(self, request):
        self._check()
        response = self.provider.complete(request)
        self._charge(request.model, response.input_tokens, response.output_tokens)
        return response

    def stream(self, request):
        self._check()
        prompt_chars = sum(len(m.content or "") for m in request.messages)
        streamed_chars = 0
        try:
            for chunk in self.provider.stream(request):
                streamed_chars += len(chunk)
                yield chunk
        finally:
            # Streamed responses carry no usage numbers, so estimate rather than
            # let /stream be a free hole in the budget.
            self._charge(
                request.model,
                _tokens_from_chars(prompt_chars),
                _tokens_from_chars(streamed_chars),
            )

    # -- introspection ------------------------------------------------------

    @property
    def usage_by_provider(self) -> dict:
        """Pass the wrapped cost tracker's per-provider stats straight through."""
        return getattr(self.provider, "usage_by_provider", {})

    def totals(self):
        inner = getattr(self.provider, "totals", None)
        if callable(inner):
            return inner()
        return UsageStats()

    @property
    def spent(self) -> float:
        with self._lock:
            self._roll_window()
            return self._spent

    @property
    def remaining(self) -> float | None:
        if self.cap_usd is None:
            return None
        return max(0.0, self.cap_usd - self.spent)

    def seconds_until_reset(self) -> float:
        with self._lock:
            self._roll_window()
            return max(0.0, self.window_seconds - (self._clock() - self._window_start))

    def snapshot(self) -> dict:
        return {
            "cap_usd": self.cap_usd,
            "spent_usd": round(self.spent, 6),
            "remaining_usd": None if self.remaining is None else round(self.remaining, 6),
            "window_seconds": self.window_seconds,
            "resets_in_seconds": int(self.seconds_until_reset()),
        }

    def reset(self) -> None:
        with self._lock:
            self._spent = 0.0
            self._window_start = self._clock()
