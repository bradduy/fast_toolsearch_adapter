# Author: Brad Duy - AI Expert
"""Utility helpers for the Tool Search Adapter."""

from __future__ import annotations

import json
from typing import Any

from .types import FunctionCall, ToolDef, ToolSearchCall


def tool_def_to_openai_tool(tool: ToolDef) -> dict[str, Any]:
    """Convert a ToolDef to the OpenAI function-calling tool schema."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def parse_tool_search_call(content: str) -> ToolSearchCall | None:
    """Extract a tool_search_call(query) from model output text.

    Supports the format: tool_search_call("query string")
    """
    marker = "tool_search_call("
    idx = content.find(marker)
    if idx == -1:
        return None

    start = idx + len(marker)
    # Find the closing paren, handling quoted strings
    rest = content[start:]
    # Try to extract a quoted string
    for quote in ('"', "'"):
        if rest.startswith(quote):
            end = rest.find(quote, 1)
            if end != -1:
                return ToolSearchCall(query=rest[1:end])

    # Fallback: take everything up to closing paren
    end = rest.find(")")
    if end != -1:
        return ToolSearchCall(query=rest[:end].strip().strip("\"'"))

    return None


def parse_function_call_from_message(message: Any) -> FunctionCall | None:
    """Extract a FunctionCall from an OpenAI chat completion message.

    Handles the tool_calls response format.
    """
    tool_calls = getattr(message, "tool_calls", None)
    if not tool_calls:
        return None

    tc = tool_calls[0]
    name = tc.function.name
    try:
        arguments = json.loads(tc.function.arguments)
    except (json.JSONDecodeError, TypeError):
        arguments = {}

    return FunctionCall(name=name, arguments=arguments)


def safe_json_parse(raw: str) -> dict[str, Any] | None:
    """Attempt to parse a JSON string; return None on failure."""
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, TypeError):
        pass
    return None
