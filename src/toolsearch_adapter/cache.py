# Author: Brad Duy - AI Expert
"""TTL cache for tool registry search results."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from .types import ToolDef


class TTLCache:
    """Simple in-memory TTL cache for registry search results.

    Keys are derived from (tenant_id, query, k, namespace, max_risk_level).
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, list[ToolDef]]] = {}

    @staticmethod
    def _make_key(
        tenant_id: str,
        query: str,
        k: int,
        namespace: str | None,
        max_risk_level: int,
    ) -> str:
        raw = json.dumps(
            {
                "tenant_id": tenant_id,
                "query": query,
                "k": k,
                "namespace": namespace,
                "max_risk_level": max_risk_level,
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(
        self,
        tenant_id: str,
        query: str,
        k: int,
        namespace: str | None = None,
        max_risk_level: int = 3,
    ) -> list[ToolDef] | None:
        """Return cached tools or None if miss/expired."""
        key = self._make_key(tenant_id, query, k, namespace, max_risk_level)
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, tools = entry
        if time.monotonic() - ts > self._ttl:
            del self._store[key]
            return None
        return tools

    def put(
        self,
        tenant_id: str,
        query: str,
        k: int,
        tools: list[ToolDef],
        namespace: str | None = None,
        max_risk_level: int = 3,
    ) -> None:
        """Store tools in cache."""
        key = self._make_key(tenant_id, query, k, namespace, max_risk_level)
        self._store[key] = (time.monotonic(), tools)

    def invalidate(self) -> None:
        """Clear all cached entries."""
        self._store.clear()

    def _evict_expired(self) -> None:
        """Remove expired entries (housekeeping)."""
        now = time.monotonic()
        expired = [k for k, (ts, _) in self._store.items() if now - ts > self._ttl]
        for k in expired:
            del self._store[k]

    @property
    def size(self) -> int:
        self._evict_expired()
        return len(self._store)
