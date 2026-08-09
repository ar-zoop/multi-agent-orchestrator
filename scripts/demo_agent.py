from dotenv import load_dotenv

from orchestrator.core.agent import Agent
from orchestrator.core.tool import Tool
from orchestrator.core.tool_registry import ToolRegistry
from orchestrator.providers.anthropic_provider import AnthropicProvider
from orchestrator.providers.openai_provider import OpenAIProvider

load_dotenv()


def get_weather(city: str) -> str:
    return f"In {city}, it's sunny and 22C."


def add_numbers(a: float, b: float) -> float:
    return a + b


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(Tool(
        name="get_weather",
        description="Get the current weather for a given city.",
        func=get_weather,
        parameters={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    ))

    registry.register(Tool(
        name="add_numbers",
        description="Add two numbers together.",
        func=add_numbers,
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
        },
    ))

    return registry


def main():
    agent = Agent.with_fallback(
        providers=[OpenAIProvider(), AnthropicProvider()],
        model="gpt-4o-mini",
        tool_registry=build_tool_registry(),
        max_iterations=5,
    )

    prompt = "What's the weather in Paris? Use the get_weather tool to find out."
    print(f"Prompt: {prompt}\n")
    print(f"Final answer: {agent.run(prompt)}\n")

    for name, stats in agent.usage_by_provider.items():
        print(f"{name}: {stats.calls} calls, ${stats.cost:.6f}")


if __name__ == "__main__":
    main()
