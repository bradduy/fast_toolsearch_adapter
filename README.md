<!-- Author: Brad Duy - AI Expert -->
# Tool Search Adapter

A production-ready Python library inspired by GPT-5.4’s Tool Search capability.  
Rather than attaching every tool schema to every request, it enables dynamic tool discovery: the model requests relevant tools at runtime, receives only the matched schemas, and then invokes the selected tool—reducing prompt bloat, improving cache efficiency, and keeping integrations scalable.

## How It Works

```
User message
    │
    ▼
┌─────────────────┐
│  LLM Call #1    │  ← system prompt enables tool search
│  (tool_search)  │
└────────┬────────┘
         │ tool_search_call("weather forecast")
         ▼
┌─────────────────┐
│  Tool Registry  │  ← search by query, returns top-k ToolDefs
│  (JSON/Postgres)│
└────────┬────────┘
         │ tool_search_output: [get_weather, ...]
         ▼
┌─────────────────┐
│  LLM Call #2    │  ← with only the discovered tool schemas
│  (function_call)│
└────────┬────────┘
         │ function_call("get_weather", {"city": "London"})
         ▼
┌─────────────────┐
│  Tool Executor  │  ← FunctionMap or HTTP
└────────┬────────┘
         │ function_call_output: {"temp": "20°C"}
         ▼
┌─────────────────┐
│  LLM Call #3    │  ← final answer
└─────────────────┘
```

## Installation

```bash
# Core (JSON registry + function map executor)
pip install toolsearch-adapter

# With Postgres registry
pip install toolsearch-adapter[postgres]

# With HTTP executor
pip install toolsearch-adapter[http]

# With FastAPI example
pip install toolsearch-adapter[fastapi]

# Everything
pip install toolsearch-adapter[all]
```

## Quickstart (JSON Registry)

```python
import asyncio
from toolsearch_adapter import (
    AdapterConfig, RiskLevel, ToolDef, ToolSearchAdapter,
)
from toolsearch_adapter.executors import FunctionMapExecutor
from toolsearch_adapter.registry import JsonRegistry

# 1. Define tools
tools = [
    ToolDef(
        name="get_weather",
        description="Get current weather for a city",
        parameters={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
        tags=["weather"],
        risk_level=RiskLevel.LOW,
    ),
]

# 2. Register handlers
def get_weather(city: str) -> dict:
    return {"city": city, "temp": "22°C", "condition": "Sunny"}

executor = FunctionMapExecutor({"get_weather": get_weather})

# 3. Create adapter
adapter = ToolSearchAdapter(
    registry=JsonRegistry(tools=tools),
    executor=executor,
    config=AdapterConfig(model="gpt-4o", max_tools=5),
)

# 4. Run
async def main():
    result = await adapter.run("my-tenant", "What's the weather in Tokyo?")
    print(result.answer)
    print(f"Tool used: {result.tool_used}")

asyncio.run(main())
```

You can also load tools from a JSON file:

```python
registry = JsonRegistry(path="tools.json")
```

Where `tools.json` looks like:

```json
[
  {
    "name": "get_weather",
    "description": "Get current weather for a city",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
    "tags": ["weather"],
    "risk_level": 1
  }
]
```

## Production Setup (Postgres Registry)

### 1. Run the migration

```bash
psql -d your_database -f migrations/001_tool_registry.sql
```

This creates the `tool_registry` table with:
- Full-text search via `tsvector` generated column + GIN index
- Multi-tenant support (`tenant_id`)
- Risk level filtering
- Namespace partitioning

### 2. Insert tools

```sql
INSERT INTO tool_registry (tenant_id, namespace, name, description, tags, parameters_schema, risk_level)
VALUES
  ('acme', 'weather', 'get_weather', 'Get current weather for a city',
   ARRAY['weather','forecast'],
   '{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}',
   1);
```

### 3. Use the Postgres registry

```python
from psycopg_pool import AsyncConnectionPool
from toolsearch_adapter import AdapterConfig, ToolSearchAdapter
from toolsearch_adapter.registry import PostgresRegistry
from toolsearch_adapter.executors import FunctionMapExecutor

pool = AsyncConnectionPool("postgresql://user:pass@localhost/mydb")
registry = PostgresRegistry(pool)

adapter = ToolSearchAdapter(
    registry=registry,
    executor=FunctionMapExecutor({...}),
    config=AdapterConfig(model="gpt-4o"),
)
```

## Configuration

```python
AdapterConfig(
    model="gpt-4o",             # OpenAI model to use
    max_tools=5,                # Top-k tools returned from search
    max_risk_level=RiskLevel.HIGH,  # Filter out CRITICAL tools
    namespace=None,             # Optional namespace constraint
    cache_ttl_seconds=300,      # TTL for registry search cache
    parallel_tool_calls=False,  # Deterministic single-tool mode
    timeout_ms=30_000,          # Tool execution timeout
    audit_enabled=True,         # Enable audit logging
    system_prompt=None,         # Override default system prompt
)
```

## Policy Filtering

```python
from toolsearch_adapter.policy import PolicyConfig

adapter = ToolSearchAdapter(
    registry=registry,
    executor=executor,
    policy=PolicyConfig(
        max_risk_level=RiskLevel.MEDIUM,   # Block HIGH and CRITICAL tools
        denylist={"delete_user"},           # Explicitly block tools by name
        allowlist={"get_weather", "calc"},  # Only allow these tools (optional)
        allowed_namespaces=["public"],      # Namespace allowlist
        require_enabled=True,              # Skip disabled tools
    ),
)
```

## Audit Logging

Tool searches and executions are automatically logged with sensitive argument masking:

```python
from toolsearch_adapter.audit import AuditLogger

# Custom masking hook
def my_mask(args: dict) -> dict:
    return {k: "***" if "secret" in k else v for k, v in args.items()}

audit = AuditLogger(enabled=True, mask_hook=my_mask)
adapter = ToolSearchAdapter(..., audit_logger=audit)

# After running, inspect entries
for entry in audit.entries:
    print(entry.event, entry.tool_name, entry.duration_ms)
```

## HTTP Executor

For tools backed by HTTP microservices:

```python
from toolsearch_adapter.executors import HttpExecutor
from toolsearch_adapter.executors.http_executor import EndpointConfig

executor = HttpExecutor(
    endpoints={
        "get_weather": EndpointConfig(
            url="https://api.internal/weather",
            method="POST",
            timeout_seconds=10,
            max_retries=2,
        ),
    },
    default_headers={"Authorization": "Bearer token"},
)
```

## FastAPI Example

See `examples/fastapi_app.py` for a complete working example:

```bash
export OPENAI_API_KEY=sk-...
pip install toolsearch-adapter[fastapi]
uvicorn examples.fastapi_app:app --reload
```

Then call:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "default", "message": "What is the weather in London?"}'
```

## Running Tests

```bash
pip install toolsearch-adapter[dev]
pytest tests/ -v
```

## Project Structure

```
src/toolsearch_adapter/
    __init__.py          # Public API exports
    adapter.py           # Core conversation loop
    types.py             # ToolDef, ToolRegistry, ToolExecutor interfaces
    policy.py            # Policy filtering (risk, namespace, allowlist)
    cache.py             # TTL cache for search results
    audit.py             # Audit logging with argument masking
    utils.py             # Parsing and conversion helpers
    registry/
        json_registry.py     # JSON file / in-memory + BM25-lite scoring
        postgres_registry.py # PostgreSQL + tsvector/GIN full-text search
    executors/
        function_map_executor.py  # name -> Python callable
        http_executor.py          # name -> HTTP endpoint
examples/
    fastapi_app.py       # FastAPI /chat endpoint
    cli_demo.py          # Interactive CLI demo
migrations/
    001_tool_registry.sql  # PostgreSQL schema + indexes
tests/                   # 58 unit tests
```

---

## Credits & Contact

Built and maintained by **Brad Duy**.

If you have questions, feature requests, or would like to collaborate, please open an issue or start a discussion in this repository.

## License

This project is released under the license specified in [`LICENSE`](./LICENSE).

---

