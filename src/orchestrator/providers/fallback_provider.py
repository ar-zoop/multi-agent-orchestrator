import logging
import time

from orchestrator.providers.base import Provider

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 422}


def is_retryable(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        return True
    if status_code in RETRYABLE_STATUS_CODES:
        return True
    if status_code in NON_RETRYABLE_STATUS_CODES:
        return False
    return status_code >= 500


class FallbackProvider(Provider):
    name = "fallback"

    def __init__(self, providers: list[Provider], circuit_breaker,
                 max_retries_per_provider: int = 2, base_delay: float = 1.0):
        self.providers = providers
        self.circuit_breaker = circuit_breaker
        self.max_retries_per_provider = max_retries_per_provider
        self.base_delay = base_delay

    def complete(self, request):
        last_error = None
        skipped = []
        for provider in self.providers:
            if self.circuit_breaker.is_open(provider.name):
                skipped.append(provider.name)
                continue

            for attempt in range(self.max_retries_per_provider):
                try:
                    response = provider.complete(request)
                    self.circuit_breaker.record_success(provider.name)
                    return response
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "provider=%s attempt=%d failed: %s", provider.name, attempt + 1, e
                    )
                    if not is_retryable(e):
                        self.circuit_breaker.record_failure(provider.name)
                        break
                    time.sleep(self.base_delay * (2 ** attempt))
            else:
                self.circuit_breaker.record_failure(provider.name)

        raise RuntimeError(self._exhausted_message(last_error, skipped))

    def stream(self, request):
        last_error = None
        skipped = []
        for provider in self.providers:
            if self.circuit_breaker.is_open(provider.name):
                skipped.append(provider.name)
                continue

            for attempt in range(self.max_retries_per_provider):
                try:
                    gen = provider.stream(request)
                    first_chunk = next(gen)
                except StopIteration:
                    self.circuit_breaker.record_success(provider.name)
                    return
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "provider=%s attempt=%d stream failed: %s", provider.name, attempt + 1, e
                    )
                    if not is_retryable(e):
                        self.circuit_breaker.record_failure(provider.name)
                        break
                    time.sleep(self.base_delay * (2 ** attempt))
                else:
                    self.circuit_breaker.record_success(provider.name)
                    yield first_chunk
                    yield from gen
                    return
            else:
                self.circuit_breaker.record_failure(provider.name)

        raise RuntimeError(self._exhausted_message(last_error, skipped))

    def _exhausted_message(self, last_error, skipped) -> str:
        if last_error is None and skipped:
            return (
                "All providers exhausted. Every provider was skipped because its "
                f"circuit breaker is open: {', '.join(skipped)}"
            )
        return f"All providers exhausted. Last error: {last_error}"
