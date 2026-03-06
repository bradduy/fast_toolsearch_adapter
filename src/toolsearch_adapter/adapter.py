# Author: Brad Duy - AI Expert
"""Core adapter implementing the GPT-5.4-style tool search conversation loop."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from openai import AsyncOpenAI

from .audit import AuditLogger
from .cache import TTLCache
from .policy import PolicyConfig, PolicyFilter
from .types import (
    AdapterConfig,
    AdapterResult,
    ToolExecutor,
    ToolRegistry,
)
from .utils import (
    parse_function_call_from_message,
    parse_tool_search_call,
    tool_def_to_openai_tool,
)

logger = logging.getLogger("toolsearch_adapter")

_TOOL_SEARCH_SYSTEM = (
    "You have access to a tool search capability. "
    "When the user's request may benefit from using a tool, "
    "emit tool_search_call(\"<your search query>\") to discover available tools. "
    "Do NOT guess tool names; always search first."
)


class ToolSearchAdapter:
    """Drives the tool-search conversation loop.

    Flow:
        1. Send user message to LLM with tool_search instruction.
        2. If LLM emits ``tool_search_call(query)``, search the registry.
        3. Send discovered tool schemas back to LLM as available tools.
        4. If LLM emits a ``function_call``, execute via the executor.
        5. Send execution result back and return the final answer.

    Args:
        registry: Tool registry to search.
        executor: Tool executor to run selected tools.
        config: Adapter configuration.
        policy: Optional policy config for filtering.
        client: Optional pre-configured AsyncOpenAI client.
        audit_logger: Optional custom audit logger.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        executor: ToolExecutor,
        config: AdapterConfig | None = None,
        policy: PolicyConfig | None = None,
        client: AsyncOpenAI | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self._registry = registry
        self._executor = executor
        self._config = config or AdapterConfig()
        self._policy = PolicyFilter(policy)
        self._client = client or AsyncOpenAI()
        self._cache = TTLCache(ttl_seconds=self._config.cache_ttl_seconds)
        self._audit = audit_logger or AuditLogger(enabled=self._config.audit_enabled)

    async def run(self, tenant_id: str, user_text: str) -> AdapterResult:
        """Execute the full tool-search conversation loop.

        Args:
            tenant_id: Tenant identifier for multi-tenant filtering.
            user_text: The user's natural language request.

        Returns:
            AdapterResult with the final answer and metadata.
        """
        cfg = self._config
        system = cfg.system_prompt or _TOOL_SEARCH_SYSTEM

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ]

        # --- Step 1: Initial LLM call (may produce tool_search_call) ---
        response = await self._chat(messages)
        message = response.choices[0].message
        content = message.content or ""

        # --- Step 2: Check for tool_search_call ---
        search_call = parse_tool_search_call(content)
        if search_call is None:
            # No tool search needed; return plain answer
            return AdapterResult(answer=content)

        # --- Step 3: Search registry ---
        t0 = time.monotonic()
        tools = await self._search_with_cache(
            tenant_id=tenant_id,
            query=search_call.query,
            k=cfg.max_tools,
        )
        search_ms = (time.monotonic() - t0) * 1000
        self._audit.log_search(tenant_id, search_call.query, len(tools), search_ms)

        if not tools:
            # No tools found; let LLM know
            messages.append({"role": "assistant", "content": content})
            messages.append({
                "role": "user",
                "content": "tool_search_output: No tools found for that query.",
            })
            response = await self._chat(messages)
            return AdapterResult(
                answer=response.choices[0].message.content or "",
                search_query=search_call.query,
                tools_found=0,
            )

        # --- Step 4: Send tool schemas back to LLM ---
        openai_tools = [tool_def_to_openai_tool(t) for t in tools]
        messages.append({"role": "assistant", "content": content})

        tool_schemas_text = json.dumps(
            [{"name": t.name, "description": t.description, "parameters": t.parameters} for t in tools],
            indent=2,
        )
        messages.append({
            "role": "user",
            "content": f"tool_search_output: Found {len(tools)} tools:
{tool_schemas_text}

You may now call one of these tools.",
        })

        response = await self._chat(messages, tools=openai_tools)
        message = response.choices[0].message

        # --- Step 5: Check for function_call ---
        fc = parse_function_call_from_message(message)
        if fc is None:
            # Model decided not to call a tool after seeing schemas
            return AdapterResult(
                answer=message.content or "",
                search_query=search_call.query,
                tools_found=len(tools),
            )

        # --- Step 6: Execute the tool ---
        if not self._executor.can_execute(fc.name):
            # Tool not executable
            messages.append(message)  # type: ignore[arg-type]
            messages.append({
                "role": "tool",
                "tool_call_id": message.tool_calls[0].id,  # type: ignore[union-attr]
                "content": json.dumps({"error": f"Tool '{fc.name}' is not available for execution."}),
            })
            response = await self._chat(messages, tools=openai_tools)
            return AdapterResult(
                answer=response.choices[0].message.content or "",
                tool_used=fc.name,
                search_query=search_call.query,
                tools_found=len(tools),
            )

        t0 = time.monotonic()
        error_msg: str | None = None
        try:
            tool_output = await self._executor.execute(fc.name, fc.arguments)
        except Exception as exc:
            tool_output = {"error": str(exc)}
            error_msg = str(exc)
        exec_ms = (time.monotonic() - t0) * 1000
        self._audit.log_execution(tenant_id, fc.name, fc.arguments, exec_ms, error_msg)

        # --- Step 7: Send result back and get final answer ---
        messages.append(message)  # type: ignore[arg-type]
        messages.append({
            "role": "tool",
            "tool_call_id": message.tool_calls[0].id,  # type: ignore[union-attr]
            "content": json.dumps(tool_output) if not isinstance(tool_output, str) else tool_output,
        })

        response = await self._chat(messages, tools=openai_tools)
        return AdapterResult(
            answer=response.choices[0].message.content or "",
            tool_used=fc.name,
            tool_output=tool_output,
            search_query=search_call.query,
            tools_found=len(tools),
        )

    async def _chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Make a chat completion call."""
        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["parallel_tool_calls"] = self._config.parallel_tool_calls
        return await self._client.chat.completions.create(**kwargs)

    async def _search_with_cache(
        self,
        tenant_id: str,
        query: str,
        k: int,
    ) -> list:
        """Search registry with caching and policy filtering."""
        cfg = self._config
        ns = cfg.namespace
        risk = int(cfg.max_risk_level)

        cached = self._cache.get(tenant_id, query, k, ns, risk)
        if cached is not None:
            return cached

        tools = await self._registry.search(
            tenant_id=tenant_id,
            query=query,
            k=k,
            namespace=ns,
            max_risk_level=cfg.max_risk_level,
        )
        tools = self._policy.filter(tools)
        self._cache.put(tenant_id, query, k, tools, ns, risk)
        return tools
