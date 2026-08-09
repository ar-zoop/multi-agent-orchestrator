from orchestrator.providers.base import Provider
from google import genai
from orchestrator.core.chat_response import ChatResponse


def _to_google_history(messages):
    history = []
    for m in messages:
        if m.role == "system":
            continue

        if m.role == "assistant" and m.tool_calls:
            for tc in m.tool_calls:
                history.append({
                    "type": "function_call",
                    "id": tc["id"],
                    "name": tc["name"],
                    "arguments": tc["arguments"],
                })

        elif m.role == "tool":
            history.append({
                "type": "function_result",
                "call_id": m.tool_call_id,
                "result": [{"type": "text", "text": m.content}],
            })

        else:
            history.append({
                "type": "user_input",
                "content": [{"type": "text", "text": m.content}],
            })

    return history


def _to_google_tools(tools):
    if not tools:
        return None
    return [
        {
            "type": "function",
            "name": t["name"],
            "description": t["description"],
            "parameters": t["parameters"],
        }
        for t in tools
    ]


class GoogleProvider(Provider):
    name = "google"
    def complete(self, request):
        client = genai.Client()
        system_messages = [m.content for m in request.messages if m.role == "system"]
        system_instruction = " ".join(system_messages) if system_messages else None

        history = _to_google_history(request.messages)

        kwargs = dict(
            model=request.model,
            system_instruction=system_instruction,
            input=history,
        )
        google_tools = _to_google_tools(request.tools)
        if google_tools:
            kwargs["tools"] = google_tools

        interaction = client.interactions.create(**kwargs)

        fc_steps = [s for s in interaction.steps if s.type == "function_call"]
        tool_calls = [
            {"id": s.id, "name": s.name, "arguments": s.arguments}
            for s in fc_steps
        ] if fc_steps else None

        stop_reason = "tool_call" if tool_calls else "final"

        chatResponse = ChatResponse(
            content=interaction.output_text or "",
            provider="google",
            input_tokens=interaction.usage.total_input_tokens,
            output_tokens=interaction.usage.total_output_tokens,
            stop_reason=stop_reason,
            tool_calls=tool_calls,
        )
        return chatResponse

    def stream(self, request):
        client = genai.Client()
        system_messages = [m.content for m in request.messages if m.role == "system"]
        system_instruction = " ".join(system_messages) if system_messages else None

        history = _to_google_history(request.messages)

        kwargs = dict(
            model=request.model,
            system_instruction=system_instruction,
            input=history,
            stream=True,
        )

        stream = client.interactions.create(**kwargs)
        for event in stream:
            if event.event_type == "step.delta" and event.delta.type == "text":
                yield event.delta.text
