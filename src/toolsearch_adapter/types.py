# Author: Brad Duy - AI Expert
"""Core types and interfaces for the Tool Search Adapter."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class RiskLevel(IntEnum):
    """Tool risk classification."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(frozen=True, slots=True)
class ToolDef:
    """Definition of a discoverable tool."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    namespace: str = ""
    tags: list[str] = field(default_factory=list)
    enabled: bool = True
    risk_level: RiskLevel = RiskLevel.LOW


@dataclass(slots=True)
class AdapterConfig:
    """Configuration for the ToolSearchAdapter."""

    model: str = "gpt-4o"
    max_tools: int = 5
    max_risk_level: RiskLevel = RiskLevel.HIGH
    namespace: str | None = None
    cache_ttl_seconds: int = 300
    parallel_tool_calls: bool = False
    timeout_ms: int = 30_000
    audit_enabled: bool = True
    system_prompt: str | None = None


@dataclass(frozen=True, slots=True)
class ToolSearchCall:
    """Parsed tool_search_call from model output."""

    query: str


@dataclass(frozen=True, slots=True)
class FunctionCall:
    """Parsed function_call from model output."""

    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AdapterResult:
    """Result returned by the adapter run."""

    answer: str
    tool_used: str | None = None
    tool_output: Any = None
    search_query: str | None = None
    tools_found: int = 0


class ToolRegistry(abc.ABC):
    """Interface for tool registries that store and search tool definitions."""

    @abc.abstractmethod
    async def search(
        self,
        tenant_id: str,
        query: str,
        k: int = 5,
        *,
        namespace: str | None = None,
        max_risk_level: RiskLevel = RiskLevel.HIGH,
    ) -> list[ToolDef]:
        """Search for tools matching a query.

        Args:
            tenant_id: Tenant identifier for multi-tenant filtering.
            query: Natural language search query.
            k: Maximum number of results to return.
            namespace: Optional namespace filter.
            max_risk_level: Exclude tools above this risk level.

        Returns:
            List of matching ToolDef objects, ranked by relevance.
        """
        ...


class ToolExecutor(abc.ABC):
    """Interface for tool executors that run discovered tools."""

    @abc.abstractmethod
    def can_execute(self, name: str) -> bool:
        """Check if this executor can handle the named tool."""
        ...

    @abc.abstractmethod
    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        """Execute a tool by name with the given arguments.

        Args:
            name: Tool name.
            arguments: Parsed arguments dict.

        Returns:
            Tool execution result (any JSON-serializable value).

        Raises:
            ValueError: If the tool cannot be executed.
            RuntimeError: If tool execution fails.
        """
        ...
