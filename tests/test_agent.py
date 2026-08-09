import pytest

from helpers import FakeAPIError, ScriptedProvider, make_response
from orchestrator.core.agent import Agent
from orchestrator.core.circuit_breaker import CircuitBreaker
from orchestrator.core.tool import Tool
from orchestrator.core.tool_registry import ToolRegistry


def echo_tool(calls=None):
    def echo(text: str) -> str:
        if calls is not None:
            calls.append(text)
        return f"echo:{text}"

    return Tool(
        name="echo",
        description="Echo the given text back.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        func=echo,
    )


def exploding_tool():
    def explode() -> str:
        raise ValueError("kaboom")

    return Tool(
        name="explode",
        description="Always raises.",
        parameters={"type": "object", "properties": {}},
        func=explode,
    )


def registry_with(*tools) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def make_agent(provider, registry=None, **kwargs):
    return Agent(
        provider=provider,
        model="gpt-4o-mini",
        tool_registry=registry if registry is not None else ToolRegistry(),
        **kwargs,
    )


def test_returns_the_answer_when_the_model_stops_immediately():
    provider = ScriptedProvider(outcomes=[make_response(content="42")])

    assert make_agent(provider).run("what is 6 times 7?") == "42"
    assert provider.call_count == 1


def test_runs_a_tool_and_feeds_the_result_back_to_the_model():
    calls = []
    provider = ScriptedProvider(outcomes=[
        make_response(
            content="",
            tool_calls=[{"id": "call_1", "name": "echo", "arguments": {"text": "hi"}}],
        ),
        make_response(content="the tool said echo:hi"),
    ])
    agent = make_agent(provider, registry_with(echo_tool(calls)))

    assert agent.run("say hi") == "the tool said echo:hi"
    assert calls == ["hi"]
    assert provider.call_count == 2

    second_request = provider.requests[1]
    roles = [m.role for m in second_request.messages]
    assert roles == ["system", "user", "assistant", "tool"]
    assert second_request.messages[-1].content == "echo:hi"
    assert second_request.messages[-1].tool_call_id == "call_1"


def test_tool_schemas_are_sent_to_the_provider():
    provider = ScriptedProvider(outcomes=[make_response(content="done")])
    make_agent(provider, registry_with(echo_tool())).run("hello")

    tools = provider.requests[0].tools
    assert [t["name"] for t in tools] == ["echo"]
    assert tools[0]["parameters"]["required"] == ["text"]


def test_no_tools_registered_sends_none_rather_than_an_empty_list():
    provider = ScriptedProvider(outcomes=[make_response(content="done")])
    make_agent(provider).run("hello")

    assert provider.requests[0].tools is None


def test_a_failing_tool_is_reported_back_to_the_model_instead_of_crashing():
    provider = ScriptedProvider(outcomes=[
        make_response(
            content="",
            tool_calls=[{"id": "call_1", "name": "explode", "arguments": {}}],
        ),
        make_response(content="recovered"),
    ])
    agent = make_agent(provider, registry_with(exploding_tool()))

    assert agent.run("break it") == "recovered"
    assert "Error executing tool explode" in provider.requests[1].messages[-1].content
    assert "kaboom" in provider.requests[1].messages[-1].content


def test_an_unregistered_tool_is_reported_back_instead_of_crashing():
    provider = ScriptedProvider(outcomes=[
        make_response(
            content="",
            tool_calls=[{"id": "call_1", "name": "nope", "arguments": {}}],
        ),
        make_response(content="recovered"),
    ])

    assert make_agent(provider).run("call a missing tool") == "recovered"
    assert "no tool named nope" in provider.requests[1].messages[-1].content


def test_a_non_final_stop_reason_with_no_tool_calls_still_returns_content():
    provider = ScriptedProvider(
        outcomes=[make_response(content="partial", stop_reason="length")]
    )

    assert make_agent(provider).run("hello") == "partial"
    assert provider.call_count == 1


def test_the_loop_gives_up_after_max_iterations():
    looping = make_response(
        content="",
        tool_calls=[{"id": "call_1", "name": "echo", "arguments": {"text": "hi"}}],
    )
    provider = ScriptedProvider(outcomes=[looping])
    agent = make_agent(provider, registry_with(echo_tool()), max_iterations=3)

    with pytest.raises(RuntimeError, match="within 3 iterations"):
        agent.run("loop forever")

    assert provider.call_count == 3


def test_the_system_prompt_is_configurable():
    provider = ScriptedProvider(outcomes=[make_response(content="ok")])
    make_agent(provider, system_prompt="You are a SQL analyst.").run("hello")

    assert provider.requests[0].messages[0].content == "You are a SQL analyst."


def test_with_fallback_uses_the_second_provider_when_the_first_is_down():
    openai = ScriptedProvider(name="openai", outcomes=[FakeAPIError(500)])
    anthropic = ScriptedProvider(name="anthropic", outcomes=[make_response("anthropic", "ok")])

    agent = Agent.with_fallback(
        providers=[openai, anthropic],
        model="gpt-4o-mini",
        tool_registry=ToolRegistry(),
        max_retries_per_provider=1,
        base_delay=0,
    )

    assert agent.run("hello") == "ok"
    assert openai.call_count == 1
    assert anthropic.call_count == 1


def test_with_fallback_tracks_cost_by_default():
    provider = ScriptedProvider(outcomes=[make_response("openai", "ok")])
    agent = Agent.with_fallback(
        providers=[provider],
        model="gpt-4o-mini",
        tool_registry=ToolRegistry(),
        base_delay=0,
    )

    agent.run("hello")

    assert agent.usage_by_provider["openai"].calls == 1


def test_with_fallback_can_skip_cost_tracking():
    provider = ScriptedProvider(outcomes=[make_response("openai", "ok")])
    agent = Agent.with_fallback(
        providers=[provider],
        model="gpt-4o-mini",
        tool_registry=ToolRegistry(),
        track_cost=False,
        base_delay=0,
    )

    agent.run("hello")

    assert agent.usage_by_provider == {}


def test_with_fallback_shares_the_circuit_breaker_it_is_given():
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
    openai = ScriptedProvider(name="openai", outcomes=[FakeAPIError(401)])
    anthropic = ScriptedProvider(name="anthropic", outcomes=[make_response("anthropic", "ok")])

    agent = Agent.with_fallback(
        providers=[openai, anthropic],
        model="gpt-4o-mini",
        tool_registry=ToolRegistry(),
        circuit_breaker=breaker,
        max_retries_per_provider=1,
        base_delay=0,
    )

    agent.run("hello")
    assert breaker.is_open("openai") is True

    agent.run("hello again")
    assert openai.call_count == 1


def test_with_fallback_requires_at_least_one_provider():
    with pytest.raises(ValueError, match="at least one provider"):
        Agent.with_fallback(providers=[], model="gpt-4o-mini", tool_registry=ToolRegistry())
