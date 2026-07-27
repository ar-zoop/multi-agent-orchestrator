from pydantic import BaseModel

class ChatResponse(BaseModel):
    content: str 
    provider: str
    input_tokens: int
    output_tokens: int
    stop_reason: str
    tool_calls: list[dict] | None = None