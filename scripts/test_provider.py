import pytest
from provider import Provider

def test_provider_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Provider()