# Author: Brad Duy - AI Expert
"""Executor that maps tool names to Python callables."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable

from ..types import ToolExecutor

Handler = Callable[..., Any]


class FunctionMapExecutor(ToolExecutor):
    """Execute tools by looking up name -> callable in a dictionary.

    Supports both sync and async handler functions.

    Example::

        executor = FunctionMapExecutor({
            "get_weather": get_weather,
            "calculate": lambda expr: eval(expr),
        })
    """

    def __init__(self, handlers: dict[str, Handler]) -> None:
        self._handlers = dict(handlers)

    def register(self, name: str, handler: Handler) -> None:
        """Register a handler for a tool name."""
        self._handlers[name] = handler

    def can_execute(self, name: str) -> bool:
        return name in self._handlers

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        handler = self._handlers.get(name)
        if handler is None:
            raise ValueError(f"No handler registered for tool '{name}'")

        try:
            if inspect.iscoroutinefunction(handler):
                return await handler(**arguments)
            else:
                return await asyncio.to_thread(handler, **arguments)
        except TypeError as exc:
            raise ValueError(f"Invalid arguments for tool '{name}': {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"Tool '{name}' execution failed: {exc}") from exc
