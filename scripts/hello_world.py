import json
import os

from dotenv import load_dotenv
from anthropic import Anthropic
from google import genai
from openai import OpenAI

from orchestrator.providers.anthropic_provider import AnthropicProvider
from orchestrator.core.chat_request import ChatRequest
from orchestrator.providers.google_provider import GoogleProvider
from orchestrator.providers.openai_provider import OpenAIProvider
from orchestrator.core.tool import Tool
from orchestrator.core.tool_registry import ToolRegistry

load_dotenv()


def get_weather(city: str) -> str:
    return f"In {city}, the weather is sunny today."

create_weather_tool = Tool(name = "get_weather", description = "Function to get the weather of a city", func = get_weather,
                   parameters = {
					"type": "object",
					"properties": {"city": {"type": "string"}},
					"required": ["city"],
				},)


def test():
    print("Starting the demo...\n")

    registry = {
        "openai": OpenAIProvider(),
        "anthropic": AnthropicProvider(),
        "google": GoogleProvider(),
    }

    provider_name = "google"
    provider = registry.get(provider_name)
    if provider is None:
        available = ", ".join(registry.keys())
        raise ValueError(f"Unknown provider: {provider_name}. Available: {available}")

    request = ChatRequest(
        model="gemini-3.5-flash",
        messages=["Please say hello in Hindi."],
        temperature=1.0,
    )
    response = provider.complete(request)
    print(f"{response.provider} says: {response.content}\n")

    tool_registry = ToolRegistry()
    tool_registry.register(create_weather_tool)

    weather_tool = tool_registry.get("get_weather")
    print(f"Weather tool output: {weather_tool.func('New York')}")
