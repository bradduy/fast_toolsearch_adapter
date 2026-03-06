# Author: Brad Duy - AI Expert
"""Tests for utility functions."""

from __future__ import annotations

from unittest.mock import MagicMock

from toolsearch_adapter import RiskLevel, ToolDef
from toolsearch_adapter.utils import (
    parse_function_call_from_message,
    parse_tool_search_call,
    safe_json_parse,
    tool_def_to_openai_tool,
)


class TestParseToolSearchCall:
    def test_basic_double_quotes(self):
        result = parse_tool_search_call('tool_search_call("weather forecast")')
        assert result is not None
        assert result.query == "weather forecast"

    def test_single_quotes(self):
        result = parse_tool_search_call("tool_search_call('math calculator')")
        assert result is not None
        assert result.query == "math calculator"

    def test_no_quotes(self):
        result = parse_tool_search_call("tool_search_call(weather)")
        assert result is not None
        assert result.query == "weather"

    def test_embedded_in_text(self):
        text = 'Let me search for tools. tool_search_call("get weather") I will help you.'
        result = parse_tool_search_call(text)
        assert result is not None
        assert result.query == "get weather"

    def test_no_tool_search(self):
        result = parse_tool_search_call("Hello, how are you?")
        assert result is None

    def test_empty_string(self):
        result = parse_tool_search_call("")
        assert result is None


class TestParseFunctionCall:
    def test_with_tool_calls(self):
        msg = MagicMock()
        tc = MagicMock()
        tc.function.name = "get_weather"
        tc.function.arguments = '{"city": "London"}'
        msg.tool_calls = [tc]

        result = parse_function_call_from_message(msg)
        assert result is not None
        assert result.name == "get_weather"
        assert result.arguments == {"city": "London"}

    def test_without_tool_calls(self):
        msg = MagicMock()
        msg.tool_calls = None
        assert parse_function_call_from_message(msg) is None

    def test_empty_tool_calls(self):
        msg = MagicMock()
        msg.tool_calls = []
        assert parse_function_call_from_message(msg) is None

    def test_bad_json_arguments(self):
        msg = MagicMock()
        tc = MagicMock()
        tc.function.name = "test"
        tc.function.arguments = "not json"
        msg.tool_calls = [tc]

        result = parse_function_call_from_message(msg)
        assert result is not None
        assert result.name == "test"
        assert result.arguments == {}


class TestSafeJsonParse:
    def test_valid_json(self):
        assert safe_json_parse('{"a": 1}') == {"a": 1}

    def test_invalid_json(self):
        assert safe_json_parse("not json") is None

    def test_non_dict_json(self):
        assert safe_json_parse("[1, 2, 3]") is None

    def test_empty_string(self):
        assert safe_json_parse("") is None


class TestToolDefToOpenAI:
    def test_conversion(self):
        tool = ToolDef(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
            risk_level=RiskLevel.LOW,
        )
        result = tool_def_to_openai_tool(tool)
        assert result["type"] == "function"
        assert result["function"]["name"] == "test_tool"
        assert result["function"]["description"] == "A test tool"
