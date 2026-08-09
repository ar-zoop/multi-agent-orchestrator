import time


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def is_open(self, provider_name: str) -> bool:
        opened_at = self._opened_at.get(provider_name)
        if opened_at is None:
            return False
        if time.monotonic() - opened_at <= self.cooldown_seconds:
            return True
        self._reset(provider_name)
        return False

    def record_success(self, provider_name: str) -> None:
        self._reset(provider_name)

    def record_failure(self, provider_name: str) -> None:
        self._failures[provider_name] = self._failures.get(provider_name, 0) + 1
        if self._failures[provider_name] >= self.failure_threshold:
            self._opened_at[provider_name] = time.monotonic()

    def failure_count(self, provider_name: str) -> int:
        return self._failures.get(provider_name, 0)

    def _reset(self, provider_name: str) -> None:
        self._failures[provider_name] = 0
        self._opened_at.pop(provider_name, None)
