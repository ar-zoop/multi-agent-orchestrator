import logging

from orchestrator.core.chat_message import Message
from orchestrator.core.chat_request import ChatRequest
from orchestrator.core.circuit_breaker import CircuitBreaker
from orchestrator.core.tool_registry import ToolRegistry
from orchestrator.providers.base import Provider
from orchestrator.providers.chain import build_provider_chain

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."


class Agent:
    def __init__(
        self,
        provider: Provider,
        model: str,
        tool_registry: ToolRegistry,
        max_iterations: int = 10,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        temperature: float = 0.3,
    ):
        self.provider = provider
        self.model = model
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations
        self.system_prompt = system_prompt
        self.temperature = temperature

    @classmethod
    def with_fallback(
        cls,
        providers: list[Provider],
        model: str,
        tool_registry: ToolRegistry,
        circuit_breaker: CircuitBreaker | None = None,
        max_retries_per_provider: int = 2,
        base_delay: float = 1.0,
        track_cost: bool = True,
        **kwargs,
    ) -> "Agent":
        chain = build_provider_chain(
            providers,
            circuit_breaker=circuit_breaker,
            max_retries_per_provider=max_retries_per_provider,
            base_delay=base_delay,
            track_cost=track_cost,
        )
        return cls(provider=chain, model=model, tool_registry=tool_registry, **kwargs)

    @property
    def usage_by_provider(self) -> dict:
        return getattr(self.provider, "usage_by_provider", {})

    def _tool_schemas(self):
        return [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in self.tool_registry.all()
        ] or None

    def _execute_tool_call(self, tool_call: dict) -> str:
        name = tool_call.get("name")
        arguments = tool_call.get("arguments") or {}
        try:
            tool = self.tool_registry.get(name)
        except KeyError:
            return f"Error: no tool named {name} is registered."
        try:
            return str(tool.func(**arguments))
        except Exception as e:
            logger.warning("tool=%s failed: %s", name, e)
            return f"Error executing tool {name}: {e}"

    def run(self, prompt: str) -> str:
        state = [
            Message(role="system", content=self.system_prompt),
            Message(role="user", content=prompt),
        ]
        tools = self._tool_schemas()

        for iteration in range(self.max_iterations):
            request = ChatRequest(
                model=self.model,
                messages=state,
                temperature=self.temperature,
                tools=tools,
            )
            response = self.provider.complete(request)

            tool_calls = response.tool_calls or []
            if response.stop_reason == "final" or not tool_calls:
                return response.content

            logger.info("iteration=%d tool_calls=%d", iteration + 1, len(tool_calls))
            state.append(Message(
                role="assistant",
                content=response.content,
                tool_calls=tool_calls,
            ))

            for tool_call in tool_calls:
                state.append(Message(
                    role="tool",
                    tool_call_id=tool_call.get("id"),
                    content=self._execute_tool_call(tool_call),
                ))

        raise RuntimeError(
            f"Agent did not reach a final answer within {self.max_iterations} iterations."
        )
