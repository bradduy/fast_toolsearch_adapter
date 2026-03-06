# Author: Brad Duy - AI Expert
"""Interactive CLI demo for the Tool Search Adapter.

Run with:
    python examples/cli_demo.py

Requires:
    pip install toolsearch-adapter
    export OPENAI_API_KEY=sk-...
"""

from __future__ import annotations

import asyncio

from toolsearch_adapter import (
    AdapterConfig,
    RiskLevel,
    ToolDef,
    ToolSearchAdapter,
)
from toolsearch_adapter.executors import FunctionMapExecutor
from toolsearch_adapter.registry import JsonRegistry

TOOLS = [
    ToolDef(
        name="get_weather",
        description="Get the current weather for a given city",
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"},
            },
            "required": ["city"],
        },
        tags=["weather", "forecast"],
        risk_level=RiskLevel.LOW,
    ),
    ToolDef(
        name="calculate",
        description="Evaluate a mathematical expression and return the result",
        parameters={
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Math expression"},
            },
            "required": ["expression"],
        },
        tags=["math", "calculator"],
        risk_level=RiskLevel.LOW,
    ),
    ToolDef(
        name="search_docs",
        description="Search internal documentation by keyword",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
        tags=["search", "documentation"],
        risk_level=RiskLevel.LOW,
    ),
]


def get_weather(city: str) -> dict:
    return {"city": city, "temperature": "22°C", "condition": "Sunny"}


def calculate(expression: str) -> dict:
    allowed = set("0123456789+-*/.(). ")
    if not all(c in allowed for c in expression):
        return {"error": "Invalid characters"}
    try:
        result = eval(expression, {"__builtins__": {}})  # noqa: S307
    except Exception as exc:
        return {"error": str(exc)}
    return {"expression": expression, "result": result}


def search_docs(query: str) -> dict:
    return {"query": query, "results": ["Doc A: Getting started", "Doc B: API reference"]}


async def main() -> None:
    registry = JsonRegistry(tools=TOOLS)
    executor = FunctionMapExecutor({
        "get_weather": get_weather,
        "calculate": calculate,
        "search_docs": search_docs,
    })
    config = AdapterConfig(model="gpt-4o", max_tools=5)
    adapter = ToolSearchAdapter(registry=registry, executor=executor, config=config)

    print("Tool Search Adapter CLI Demo")
    print("Type 'quit' to exit.
")

    while True:
        user_input = input("You: ").strip()
        if not user_input or user_input.lower() in ("quit", "exit"):
            break

        result = await adapter.run(tenant_id="demo", user_text=user_input)
        print(f"
Assistant: {result.answer}")
        if result.tool_used:
            print(f"  [Tool used: {result.tool_used}]")
        if result.search_query:
            print(f"  [Search query: {result.search_query}, tools found: {result.tools_found}]")
        print()


if __name__ == "__main__":
    asyncio.run(main())
