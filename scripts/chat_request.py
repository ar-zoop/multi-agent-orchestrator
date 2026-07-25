from pydantic import BaseModel

class ChatRequest(BaseModel):
    messages: list[str]
    model: str
    temperature: float
    