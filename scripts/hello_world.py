import json
import os

from dotenv import load_dotenv
from anthropic import Anthropic
from openai import OpenAI

load_dotenv()


def get_weather(city: str) -> str:
    print("inside the function")
    return f"In {city}, the weather is sunny."

TOOLS_OPENAI = [
    {
        "function": {
            "name": "get_weather",
            "description": "Function to get the weather of a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
        "type": "function",
    }
]

TOOLS_ANTHROPIC = [
    {
        "input_schema": {
            "type":"object",
            "properties":{"city": {"type": "string"}},
            "required": ["city"]
            },
        "name": "get_weather",
        "description": "Function to get the weather of a city",
    }
]

TOOL_MAP = {"get_weather": get_weather}


def call_anthropic():
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    Messages = [{"role": "user", "content": "Whats the weather in san francisco?"}]
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=100,
        messages=Messages,
        tools=TOOLS_ANTHROPIC
    )
    if response.stop_reason == "tool_use":
        func_to_call = TOOL_MAP.get(response.content[0].name)
        args = response.content[0].input
        res=func_to_call(**args)
        Messages.append({
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": response.content[0].id,
                    "name": response.content[0].name,
                    "input": response.content[0].input
                }
            ]
        })
        Messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": response.content[0].id,
                    "content": res
                }
            ]
        })
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=100,
            messages=Messages
        )
        print(response.content[0].text)
    else :
        print(response.content[0].text)    


def call_openai():
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    messages = [{"role": "user", "content": "Whats the weather in New York City?"}]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        stream=False,
        tools=TOOLS_OPENAI,
    )

    tool_calls = response.choices[0].message.tool_calls
    if not tool_calls:
        print(response.choices[0].message.content)
        return

    tool_call = tool_calls[0]
    func_name = tool_call.function.name
    raw_arguments = tool_call.function.arguments
    arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments

    func_to_call = TOOL_MAP.get(func_name)
    if func_to_call is None:
        raise ValueError(f"Unknown tool: {func_name}")

    result = func_to_call(**arguments)

    messages.append(response.choices[0].message)
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result,
        }
    )

    followup = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
    )
    print(followup.choices[0].message.content)


if __name__ == "__main__":
    # call_openai()
    call_anthropic()