import os
from abc import ABC, abstractmethod


class MissingAPIKeyError(RuntimeError):
    status_code = 401

    def __init__(self, provider_name: str, env_vars: tuple[str, ...]):
        self.provider_name = provider_name
        self.env_vars = env_vars
        super().__init__(
            f"{provider_name} is not configured: set {' or '.join(env_vars)}"
        )


def require_api_key(provider_name: str, *env_vars: str) -> str:
    for name in env_vars:
        value = os.getenv(name)
        if value:
            return value
    raise MissingAPIKeyError(provider_name, env_vars)


class Provider(ABC):

    @abstractmethod
    def complete(self, request):
        pass

    @abstractmethod
    def stream(self, request):
        pass
