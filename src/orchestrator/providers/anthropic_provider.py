from orchestrator.providers.base import Provider
from anthropic import Anthropic
from orchestrator.core.chat_response import ChatResponse
import os


def _to_anthropic_messages(messages):
    system_parts = [m.content for m in messages if m.role == "system"]
    system = " ".join(system_parts) if system_parts else None

    anthropic_messages = []
    for m in messages:
        if m.role == "system":
            continue

        if m.role == "assistant" and m.tool_calls:
            content = []
            if m.content:
                content.append({"type": "text", "text": m.content})
            for tc in m.tool_calls:
                content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["arguments"],
                })
            anthropic_messages.append({"role": "assistant", "content": content})

        elif m.role == "tool":
            anthropic_messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": m.tool_call_id,
                        "content": m.content,
                    }
                ],
            })

        else:
            anthropic_messages.append({"role": m.role, "content": m.content})

    return system, anthropic_messages


def _to_anthropic_tools(tools):
    if not tools:
        return None
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["parameters"],
        }
        for t in tools
    ]


class AnthropicProvider(Provider):
    name = "anthropic"
    def complete(self, request):
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        system, anthropic_messages = _to_anthropic_messages(request.messages)

        kwargs = dict(
            model=request.model,
            max_tokens=1024,
            messages=anthropic_messages,
            temperature=request.temperature,
        )
        if system:
            kwargs["system"] = system

        anthropic_tools = _to_anthropic_tools(request.tools)
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        response = client.messages.create(**kwargs)

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        tool_calls = [
            {"id": b.id, "name": b.name, "arguments": b.input}
            for b in tool_use_blocks
        ] if tool_use_blocks else None

        text_blocks = [b.text for b in response.content if b.type == "text"]
        content = text_blocks[0] if text_blocks else ""

        stop_reason = "tool_call" if tool_calls else "final"

        chatResponse = ChatResponse(
            content=content,
            provider="anthropic",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            tool_calls=tool_calls,
            stop_reason=stop_reason)

        return chatResponse
    
    def stream(self, request):
        # tool calling not supported in streaming mode
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        system, anthropic_messages = _to_anthropic_messages(request.messages)   
        kwargs = dict(
                    model=request.model,
                    max_tokens=1024,
                    messages=anthropic_messages,
                    temperature=request.temperature,
                )
        if system:
            kwargs["system"] = system
        
        response = client.messages.stream(**kwargs)
        with response as stream:
            for chunk in stream:
                if chunk.type=="content_block_delta":
                    yield chunk.delta.text
                
                  
