# Author: Brad Duy - AI Expert
"""Tests for executor implementations."""

from __future__ import annotations

import pytest

from toolsearch_adapter.executors import FunctionMapExecutor


class TestFunctionMapExecutor:
    @pytest.fixture
    def executor(self):
        return FunctionMapExecutor({
            "greet": lambda name: f"Hello, {name}!",
            "add": lambda a, b: a + b,
        })

    def test_can_execute(self, executor):
        assert executor.can_execute("greet") is True
        assert executor.can_execute("nonexistent") is False

    @pytest.mark.asyncio
    async def test_execute_sync_handler(self, executor):
        result = await executor.execute("greet", {"name": "World"})
        assert result == "Hello, World!"

    @pytest.mark.asyncio
    async def test_execute_with_multiple_args(self, executor):
        result = await executor.execute("add", {"a": 2, "b": 3})
        assert result == 5

    @pytest.mark.asyncio
    async def test_execute_async_handler(self):
        async def async_greet(name: str) -> str:
            return f"Async hello, {name}!"

        executor = FunctionMapExecutor({"greet": async_greet})
        result = await executor.execute("greet", {"name": "World"})
        assert result == "Async hello, World!"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, executor):
        with pytest.raises(ValueError, match="No handler"):
            await executor.execute("unknown", {})

    @pytest.mark.asyncio
    async def test_execute_bad_args(self, executor):
        with pytest.raises(ValueError, match="Invalid arguments"):
            await executor.execute("greet", {"wrong_param": "value"})

    @pytest.mark.asyncio
    async def test_execute_handler_exception(self):
        def failing() -> None:
            raise RuntimeError("boom")

        executor = FunctionMapExecutor({"fail": failing})
        with pytest.raises(RuntimeError, match="execution failed"):
            await executor.execute("fail", {})

    def test_register_handler(self):
        executor = FunctionMapExecutor({})
        assert not executor.can_execute("new_tool")
        executor.register("new_tool", lambda: "ok")
        assert executor.can_execute("new_tool")
