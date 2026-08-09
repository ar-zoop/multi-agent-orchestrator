import pytest

from orchestrator.core.tool import Tool
from orchestrator.core.tool_registry import ToolRegistry


def make_tool(name="echo"):
    return Tool(
        name=name,
        description="Echo text back.",
        parameters={"type": "object", "properties": {}},
        func=lambda: "ok",
    )


def test_a_registered_tool_can_be_looked_up_by_name():
    registry = ToolRegistry()
    tool = make_tool()
    registry.register(tool)

    assert registry.get("echo") is tool
    assert registry.has("echo") is True
    assert registry.names() == ["echo"]
    assert len(registry) == 1


def test_looking_up_an_unknown_tool_raises_key_error():
    with pytest.raises(KeyError):
        ToolRegistry().get("missing")


def test_registering_the_same_name_twice_is_rejected():
    registry = ToolRegistry()
    registry.register(make_tool())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(make_tool())


def test_two_registries_do_not_share_state():
    first = ToolRegistry()
    second = ToolRegistry()
    first.register(make_tool())

    assert len(first) == 1
    assert len(second) == 0


def test_all_returns_every_registered_tool():
    registry = ToolRegistry()
    registry.register(make_tool("a"))
    registry.register(make_tool("b"))

    assert sorted(t.name for t in registry.all()) == ["a", "b"]
