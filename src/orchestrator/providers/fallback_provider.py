import time
from orchestrator.providers.base import Provider

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

def is_retryable(exc: Exception) -> bool:
    try :
        if exc.status_code in RETRYABLE_STATUS_CODES:
            return True
        elif exc.status_code in [401, 400]:
            return False
        return True
    except AttributeError:
        return True
    except Exception as e:
        print(f"Unexpected error in is_retryable: {exc}")
        return False
    
class FallbackProvider(Provider):
    def __init__(self, providers: list[Provider], circuit_breaker,
                 max_retries_per_provider: int = 2, base_delay: float = 1.0):
        self.providers = providers
        self.circuit_breaker = circuit_breaker
        self.max_retries_per_provider = max_retries_per_provider
        self.base_delay = base_delay

    def complete(self, request):
        last_error = None
        for provider in self.providers:
            if self.circuit_breaker.is_open(provider.name):
                continue

            for attempt in range(self.max_retries_per_provider):
                try:
                    response = provider.complete(request)
                    self.circuit_breaker.record_success(provider.name)
                    return response
                except Exception as e:
                    last_error = e
                    if not is_retryable(e):
                        self.circuit_breaker.record_failure(provider.name)
                        break
                    time.sleep(self.base_delay * (2 ** attempt))
            else:
                self.circuit_breaker.record_failure(provider.name)
                continue        
        
        raise RuntimeError(f"All providers exhausted. Last error: {last_error}")
    
    def stream(self, request):
        last_error = None
        for provider in self.providers:
            if self.circuit_breaker.is_open(provider.name):
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
                continue

        raise RuntimeError(f"All providers exhausted. Last error: {last_error}")