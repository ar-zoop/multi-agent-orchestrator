import pytest

from helpers import FIXTURES
from orchestrator.core.circuit_breaker import CircuitBreaker


@pytest.fixture
def breaker():
    return CircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)


@pytest.fixture
def sample_diff():
    return (FIXTURES / "sample_pr.diff").read_text()
