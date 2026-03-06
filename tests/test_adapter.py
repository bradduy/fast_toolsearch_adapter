# Author: Brad Duy - AI Expert
"""Tests for the core adapter loop."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from toolsearch_adapter import (
    AdapterConfig,
    RiskLevel,
    ToolDef,
    ToolSearchAdapter,
)
from toolsearch_adapter.executors import FunctionMapExecutor
from toolsearch_adapter.registry import JsonRegistry

SAMPLE_TOOLS = [
    ToolDef(
        name="get_weather",
        description="Get current weather for a city",
        parameters={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
        tags=["weather"],
        risk_level=RiskLevel.LOW,
    ),
    ToolDef(
        name="calculate",
        description="Evaluate a math expression",
        parameters={
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
        tags=["math"],
        risk_level=RiskLevel.LOW,
    ),
]


def _make_message(content: str | None = None, tool_calls: list | None = None):
    """Create a mock message object."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    return msg


def _make_tool_call(name: str, arguments: dict):
    """Create a mock tool_call object."""
    tc = MagicMock()
    tc.id = "call_123"
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


def _make_response(message):
    """Wrap a message in a mock response."""
    resp = MagicMock()
    resp.choices = [MagicMock(message=message)]
    return resp


@pytest.fixture
def registry():
    return JsonRegistry(tools=SAMPLE_TOOLS)


@pytest.fixture
def executor():
    return FunctionMapExecutor({
        "get_weather": lambda city: {"city": city, "temp": "20°C"},
        "calculate": lambda expression: {"result": eval(expression, {"__builtins__": {}})},
    })


@pytest.fixture
def config():
    return AdapterConfig(model="gpt-4o", max_tools=5, audit_enabled=False)


class TestToolSearchPath:
    """Test the full tool_search_call -> function_call -> result path."""

    @pytest.mark.asyncio
    async def test_full_tool_search_flow(self, registry, executor, config):
        """Adapter searches, calls tool, returns final answer."""
        mock_client = AsyncMock()

        # Call 1: LLM emits tool_search_call
        msg1 = _make_message(content='tool_search_call("weather forecast")')
        # Call 2: LLM emits function_call after seeing tool schemas
        tc = _make_tool_call("get_weather", {"city": "London"})
        msg2 = _make_message(content=None, tool_calls=[tc])
        # Call 3: LLM produces final answer after seeing tool output
        msg3 = _make_message(content="The weather in London is 20°C.")

        mock_client.chat.completions.create = AsyncMock(
            side_effect=[_make_response(msg1), _make_response(msg2), _make_response(msg3)]
        )

        adapter = ToolSearchAdapter(
            registry=registry, executor=executor, config=config, client=mock_client
        )
        result = await adapter.run("tenant1", "What's the weather in London?")

        assert result.answer == "The weather in London is 20°C."
        assert result.tool_used == "get_weather"
        assert result.search_query == "weather forecast"
        assert result.tools_found > 0

    @pytest.mark.asyncio
    async def test_no_tools_found(self, executor, config):
        """When registry returns no tools, adapter tells LLM and returns answer."""
        empty_registry = JsonRegistry(tools=[])
        mock_client = AsyncMock()

        msg1 = _make_message(content='tool_search_call("nonexistent tool")')
        msg2 = _make_message(content="I couldn't find any tools for that.")

        mock_client.chat.completions.create = AsyncMock(
            side_effect=[_make_response(msg1), _make_response(msg2)]
        )

        adapter = ToolSearchAdapter(
            registry=empty_registry, executor=executor, config=config, client=mock_client
        )
        result = await adapter.run("tenant1", "Do something impossible")

        assert "couldn't find" in result.answer.lower() or result.tools_found == 0
        assert result.tool_used is None


class TestNoToolPath:
    """Test the path where no tool search is needed."""

    @pytest.mark.asyncio
    async def test_no_tool_search_call(self, registry, executor, config):
        """When LLM doesn't emit tool_search_call, return direct answer."""
        mock_client = AsyncMock()

        msg = _make_message(content="Hello! How can I help you today?")
        mock_client.chat.completions.create = AsyncMock(return_value=_make_response(msg))

        adapter = ToolSearchAdapter(
            registry=registry, executor=executor, config=config, client=mock_client
        )
        result = await adapter.run("tenant1", "Hi there")

        assert result.answer == "Hello! How can I help you today?"
        assert result.tool_used is None
        assert result.search_query is None

    @pytest.mark.asyncio
    async def test_model_declines_tool_after_search(self, registry, executor, config):
        """Model sees tools but decides not to use any."""
        mock_client = AsyncMock()

        msg1 = _make_message(content='tool_search_call("weather")')
        msg2 = _make_message(content="I can answer that without a tool: it's typically warm.")

        mock_client.chat.completions.create = AsyncMock(
            side_effect=[_make_response(msg1), _make_response(msg2)]
        )

        adapter = ToolSearchAdapter(
            registry=registry, executor=executor, config=config, client=mock_client
        )
        result = await adapter.run("tenant1", "Is it warm in summer?")

        assert result.tool_used is None
        assert result.tools_found > 0


class TestFunctionCallExecution:
    """Test function_call execution paths."""

    @pytest.mark.asyncio
    async def test_tool_execution_error(self, registry, config):
        """When tool execution raises, adapter sends error to LLM."""
        failing_executor = FunctionMapExecutor({
            "get_weather": lambda city: (_ for _ in ()).throw(RuntimeError("API down")),
        })
        mock_client = AsyncMock()

        msg1 = _make_message(content='tool_search_call("weather")')
        tc = _make_tool_call("get_weather", {"city": "Paris"})
        msg2 = _make_message(content=None, tool_calls=[tc])
        msg3 = _make_message(content="Sorry, the weather service is unavailable.")

        mock_client.chat.completions.create = AsyncMock(
            side_effect=[_make_response(msg1), _make_response(msg2), _make_response(msg3)]
        )

        adapter = ToolSearchAdapter(
            registry=registry, executor=failing_executor, config=config, client=mock_client
        )
        result = await adapter.run("tenant1", "Weather in Paris?")

        assert result.tool_used == "get_weather"
        assert "unavailable" in result.answer.lower() or result.tool_output is not None

    @pytest.mark.asyncio
    async def test_tool_not_executable(self, registry, config):
        """When executor can't handle the tool, adapter sends error to LLM."""
        empty_executor = FunctionMapExecutor({})
        mock_client = AsyncMock()

        msg1 = _make_message(content='tool_search_call("weather")')
        tc = _make_tool_call("get_weather", {"city": "Berlin"})
        msg2 = _make_message(content=None, tool_calls=[tc])
        msg3 = _make_message(content="That tool isn't available right now.")

        mock_client.chat.completions.create = AsyncMock(
            side_effect=[_make_response(msg1), _make_response(msg2), _make_response(msg3)]
        )

        adapter = ToolSearchAdapter(
            registry=registry, executor=empty_executor, config=config, client=mock_client
        )
        result = await adapter.run("tenant1", "Weather in Berlin?")

        assert result.tool_used == "get_weather"


class TestBadJsonArgs:
    """Test handling of invalid JSON arguments from the model."""

    @pytest.mark.asyncio
    async def test_bad_json_args_fallback(self, registry, executor, config):
        """When model sends bad JSON args, parse_function_call returns empty dict."""
        mock_client = AsyncMock()

        msg1 = _make_message(content='tool_search_call("weather")')

        # Create tool call with invalid JSON
        tc = MagicMock()
        tc.id = "call_bad"
        tc.function.name = "get_weather"
        tc.function.arguments = "not valid json{{"
        msg2 = _make_message(content=None, tool_calls=[tc])

        # The executor will be called with empty dict, which will fail
        msg3 = _make_message(content="I had trouble with the tool arguments.")

        mock_client.chat.completions.create = AsyncMock(
            side_effect=[_make_response(msg1), _make_response(msg2), _make_response(msg3)]
        )

        adapter = ToolSearchAdapter(
            registry=registry, executor=executor, config=config, client=mock_client
        )
        result = await adapter.run("tenant1", "Weather?")

        # Should still get a result (adapter handles the error gracefully)
        assert result.answer is not None
        assert result.tool_used == "get_weather"
