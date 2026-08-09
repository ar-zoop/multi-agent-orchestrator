import pytest
from orchestrator.core.chat_request import ChatRequest
from pydantic import ValidationError

def test_chat_request_requires_all_fields():
    with pytest.raises(ValidationError):
        ChatRequest(model="gpt-4o-mini")
