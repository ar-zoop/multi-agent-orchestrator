import pytest
from orchestrator.providers.base import Provider

def test_provider_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Provider()