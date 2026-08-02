from pydantic import BaseModel
from orchestrator.core.chat_message import Message

class ChatRequest(BaseModel):
    messages: list[Message]
    model: str
    temperature: float
    tools: list[dict] | None = None
