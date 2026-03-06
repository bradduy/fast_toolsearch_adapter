# Author: Brad Duy - AI Expert
"""Tests for the JSON registry."""

from __future__ import annotations

import pytest

from toolsearch_adapter import RiskLevel, ToolDef
from toolsearch_adapter.registry import JsonRegistry

TOOLS = [
    ToolDef(
        name="get_weather",
        description="Get current weather forecast for a city",
        parameters={"type": "object", "properties": {"city": {"type": "string"}}},
        tags=["weather", "forecast"],
        risk_level=RiskLevel.LOW,
    ),
    ToolDef(
        name="calculate",
        description="Evaluate a mathematical expression",
        parameters={"type": "object", "properties": {"expression": {"type": "string"}}},
        tags=["math", "calculator"],
        risk_level=RiskLevel.LOW,
    ),
    ToolDef(
        name="delete_user",
        description="Delete a user account permanently",
        parameters={"type": "object", "properties": {"user_id": {"type": "string"}}},
        tags=["admin", "destructive"],
        risk_level=RiskLevel.CRITICAL,
        namespace="admin",
    ),
    ToolDef(
        name="disabled_tool",
        description="This tool is disabled",
        parameters={},
        tags=["test"],
        enabled=False,
    ),
]


@pytest.fixture
def registry():
    return JsonRegistry(tools=TOOLS)


class TestJsonRegistry:
    @pytest.mark.asyncio
    async def test_search_basic(self, registry):
        results = await registry.search("t1", "weather forecast", k=5)
        assert len(results) > 0
        assert results[0].name == "get_weather"

    @pytest.mark.asyncio
    async def test_search_math(self, registry):
        results = await registry.search("t1", "calculate math expression", k=5)
        assert any(t.name == "calculate" for t in results)

    @pytest.mark.asyncio
    async def test_excludes_disabled(self, registry):
        results = await registry.search("t1", "test disabled", k=10)
        names = [t.name for t in results]
        assert "disabled_tool" not in names

    @pytest.mark.asyncio
    async def test_risk_level_filter(self, registry):
        results = await registry.search(
            "t1", "delete user admin", k=10, max_risk_level=RiskLevel.MEDIUM
        )
        names = [t.name for t in results]
        assert "delete_user" not in names

    @pytest.mark.asyncio
    async def test_namespace_filter(self, registry):
        results = await registry.search("t1", "delete user", k=10, namespace="admin")
        names = [t.name for t in results]
        assert "get_weather" not in names

    @pytest.mark.asyncio
    async def test_empty_query(self, registry):
        results = await registry.search("t1", "", k=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_k_limit(self, registry):
        results = await registry.search("t1", "tool", k=1)
        assert len(results) <= 1
