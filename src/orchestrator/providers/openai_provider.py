import json
import os

from orchestrator.providers.base import Provider
from openai import OpenAI
from orchestrator.core.chat_response import ChatResponse


def _to_openai_message(m):
    msg = {"role": m.role, "content": m.content}
    if m.role == "assistant" and m.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc["arguments"]),
                },
            }
            for tc in m.tool_calls
        ]
    if m.role == "tool" and m.tool_call_id:
        msg["tool_call_id"] = m.tool_call_id
    return msg


def _to_openai_tools(tools):
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in tools
    ]


class OpenAIProvider(Provider):
    name = "openai"
    def complete(self, request):
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        kwargs = dict(
            model=request.model,
            messages=[_to_openai_message(s) for s in request.messages],
            temperature=request.temperature,
        )
        openai_tools = _to_openai_tools(request.tools)
        if openai_tools:
            kwargs["tools"] = openai_tools

        response = client.chat.completions.create(**kwargs)

        if response.choices[0].message.tool_calls:
            tool_calls = [{
                "id": s.id,
                "name": s.function.name,
                "arguments": json.loads(s.function.arguments)
            } for s in response.choices[0].message.tool_calls]
        else:
            tool_calls = None

        # normalize OpenAI's "tool_calls"/"stop"/etc into a consistent stop_reason
        stop_reason = "tool_call" if tool_calls else "final"

        chatResponse = ChatResponse(
            content=response.choices[0].message.content or "",
            provider="openai",
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            stop_reason=stop_reason,
            tool_calls=tool_calls)
        return chatResponse


    def stream(self, request):
        # tool calling not supported in streaming mode
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        kwargs = dict(
            model=request.model,
            messages=[_to_openai_message(s) for s in request.messages],
            temperature=request.temperature,
            stream = True
        )
        response = client.chat.completions.create(**kwargs)
    
        for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content