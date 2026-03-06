# Author: Brad Duy - AI Expert
"""Executor that routes tool calls to HTTP endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..types import ToolExecutor


@dataclass(frozen=True, slots=True)
class EndpointConfig:
    """Configuration for a single HTTP tool endpoint."""

    url: str
    method: str = "POST"
    headers: dict[str, str] | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 2


class HttpExecutor(ToolExecutor):
    """Execute tools by calling HTTP endpoints via httpx.

    Args:
        endpoints: Mapping of tool name -> EndpointConfig.
        default_headers: Headers applied to every request.
    """

    def __init__(
        self,
        endpoints: dict[str, EndpointConfig],
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self._endpoints = dict(endpoints)
        self._default_headers = default_headers or {}

    def can_execute(self, name: str) -> bool:
        return name in self._endpoints

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        cfg = self._endpoints.get(name)
        if cfg is None:
            raise ValueError(f"No endpoint configured for tool '{name}'")

        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError(
                "httpx is required for HttpExecutor. Install with: pip install toolsearch-adapter[http]"
            ) from exc

        headers = {**self._default_headers, **(cfg.headers or {})}
        last_exc: Exception | None = None

        for attempt in range(1, cfg.max_retries + 2):
            try:
                async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
                    response = await client.request(
                        method=cfg.method,
                        url=cfg.url,
                        json=arguments,
                        headers=headers,
                    )
                    response.raise_for_status()
                    return response.json()
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt > cfg.max_retries:
                    break

        raise RuntimeError(
            f"Tool '{name}' HTTP call failed after {cfg.max_retries + 1} attempts: {last_exc}"
        )
