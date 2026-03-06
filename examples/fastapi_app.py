# Author: Brad Duy - AI Expert
"""Minimal FastAPI example using the Tool Search Adapter.

Run with:
    uvicorn examples.fastapi_app:app --reload

Requires:
    pip install toolsearch-adapter[fastapi]
    export OPENAI_API_KEY=sk-...
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from toolsearch_adapter import (
    AdapterConfig,
    RiskLevel,
    ToolDef,
    ToolSearchAdapter,
)
from toolsearch_adapter.executors import FunctionMapExecutor
from toolsearch_adapter.registry import JsonRegistry

# --- Tool definitions ---

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
                "expression": {"type": "string", "description": "Math expression to evaluate"},
            },
            "required": ["expression"],
        },
        tags=["math", "calculator"],
        risk_level=RiskLevel.LOW,
    ),
]


# --- Tool handlers ---

def get_weather(city: str) -> dict:
    """Stub weather handler."""
    return {"city": city, "temperature": "22°C", "condition": "Sunny"}


def calculate(expression: str) -> dict:
    """Simple calculator (restricted eval)."""
    allowed = set("0123456789+-*/.(). ")
    if not all(c in allowed for c in expression):
        return {"error": "Invalid characters in expression"}
    try:
        result = eval(expression, {"__builtins__": {}})  # noqa: S307
    except Exception as exc:
        return {"error": str(exc)}
    return {"expression": expression, "result": result}


# --- App setup ---

registry = JsonRegistry(tools=TOOLS)
executor = FunctionMapExecutor({
    "get_weather": get_weather,
    "calculate": calculate,
})
config = AdapterConfig(model="gpt-4o", max_tools=5)
adapter = ToolSearchAdapter(registry=registry, executor=executor, config=config)

app = FastAPI(title="Tool Search Adapter Demo")


class ChatRequest(BaseModel):
    tenant_id: str = "default"
    message: str


class ChatResponse(BaseModel):
    answer: str
    tool_used: str | None = None
    search_query: str | None = None
    tools_found: int = 0


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    result = await adapter.run(tenant_id=req.tenant_id, user_text=req.message)
    return ChatResponse(
        answer=result.answer,
        tool_used=result.tool_used,
        search_query=result.search_query,
        tools_found=result.tools_found,
    )
