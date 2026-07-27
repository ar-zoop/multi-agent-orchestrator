from pydantic import BaseModel
from chat_message import Message

class ChatRequest(BaseModel):
    messages: list[Message]
    model: str
    temperature: float
    tools: list[dict] | None = None
