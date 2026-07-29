import time

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def is_open(self, provider_name: str) -> bool:
        if(provider_name in self._opened_at and self._opened_at[provider_name] > 0 and time.monotonic() - self._opened_at[provider_name] <= self.cooldown_seconds ):
            return True
        return False

    def record_success(self, provider_name: str) -> None:
        self._failures[provider_name] = 0
        self._opened_at[provider_name] = -1

    def record_failure(self, provider_name: str) -> None:
        if(provider_name not in self._failures):
            self._failures[provider_name] = 1
        else:
            self._failures[provider_name] += 1
        
        if (self._failures[provider_name] >= self.failure_threshold):
            self._opened_at[provider_name] = time.monotonic()
        