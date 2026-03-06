# Author: Brad Duy - AI Expert
"""Audit logging with argument masking for tool calls."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("toolsearch_adapter.audit")

# Default sensitive keys to mask in arguments
DEFAULT_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "credit_card",
        "ssn",
        "social_security",
    }
)


@dataclass(slots=True)
class AuditEntry:
    """A single audit log entry."""

    event: str
    tenant_id: str
    timestamp: float = field(default_factory=time.time)
    tool_name: str | None = None
    query: str | None = None
    arguments: dict[str, Any] | None = None
    duration_ms: float | None = None
    tools_found: int | None = None
    error: str | None = None


MaskHook = Callable[[dict[str, Any]], dict[str, Any]]


def default_mask(
    args: dict[str, Any],
    sensitive_keys: frozenset[str] = DEFAULT_SENSITIVE_KEYS,
) -> dict[str, Any]:
    """Mask values for keys that look sensitive."""
    masked = {}
    for k, v in args.items():
        if k.lower() in sensitive_keys:
            masked[k] = "***MASKED***"
        elif isinstance(v, dict):
            masked[k] = default_mask(v, sensitive_keys)
        else:
            masked[k] = v
    return masked


class AuditLogger:
    """Structured audit logger with pluggable masking."""

    def __init__(
        self,
        enabled: bool = True,
        mask_hook: MaskHook | None = None,
    ) -> None:
        self._enabled = enabled
        self._mask_hook = mask_hook or default_mask
        self._entries: list[AuditEntry] = []

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def log_search(
        self,
        tenant_id: str,
        query: str,
        tools_found: int,
        duration_ms: float,
    ) -> None:
        if not self._enabled:
            return
        entry = AuditEntry(
            event="tool_search",
            tenant_id=tenant_id,
            query=query,
            tools_found=tools_found,
            duration_ms=duration_ms,
        )
        self._entries.append(entry)
        logger.info(
            "tool_search tenant=%s query=%r found=%d duration_ms=%.1f",
            tenant_id,
            query,
            tools_found,
            duration_ms,
        )

    def log_execution(
        self,
        tenant_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        duration_ms: float,
        error: str | None = None,
    ) -> None:
        if not self._enabled:
            return
        masked = self._mask_hook(arguments)
        entry = AuditEntry(
            event="tool_execution",
            tenant_id=tenant_id,
            tool_name=tool_name,
            arguments=masked,
            duration_ms=duration_ms,
            error=error,
        )
        self._entries.append(entry)
        logger.info(
            "tool_execution tenant=%s tool=%s args=%s duration_ms=%.1f error=%s",
            tenant_id,
            tool_name,
            masked,
            duration_ms,
            error,
        )
