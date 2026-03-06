<!-- Author: Brad Duy - AI Expert -->
# Implementation Plan: Tool Search Adapter (GPT-5.4-style)

## Goal
Build a reusable **Tool Search Adapter** that any project can drop in to get GPT-5.4-style tool discovery:
- The model requests tool discovery (`tool_search_call`)
- The app searches a Tool Registry (DB / JSON / MCP / etc.)
- The app returns `tool_search_output` (tool schemas)
- The model selects and calls a tool (`function_call`)
- The app executes the tool and returns `function_call_output`
- The model produces the final answer

This plan targets a **production-ready** adapter with:
- Multi-tenant support
- Tool policies (enabled, risk level, roles)
- Caching and audit logging
- Pluggable registry and executor backends

---

## Non-Goals
- Building a full agent framework (planning, memory, long-running workflows)
- Providing a UI
- Implementing every storage backend (we define interfaces; provide Postgres + JSON ref impls)

---

## Architecture Overview

### Components
1. **Adapter (core library)**
   - Drives the conversation loop and tool execution
2. **Tool Registry**
   - Stores tool metadata + schemas
   - Provides search (`search(tenant_id, query, k) -> tools`)
3. **Tool Executor**
   - Executes selected tool by name using handlers (internal functions or HTTP/gRPC)
4. **Policy Layer**
   - Filters tools by tenant, enabled, risk level, roles, environment
5. **Cache**
   - Caches search results and/or resolved tool schemas
6. **Audit Logger**
   - Logs tool selection and calls (with masking)

### Data Flow
1. User message → Adapter → LLM request (with `tool_search` enabled)
2. If LLM emits `tool_search_call`:
   - Adapter → ToolRegistry.search() → top-k tools
   - Adapter → sends `tool_search_output` with tool schemas
3. If LLM emits `function_call`:
   - Adapter → ToolExecutor.execute() → result
   - Adapter → sends `function_call_output` back to LLM
4. LLM returns final answer → Adapter returns answer to caller

---

## Repo Layout

```text
toolsearch-adapter/
  src/
    toolsearch_adapter/
      __init__.py
      adapter.py
      types.py
      registry/
        __init__.py
        base.py
        json_registry.py
        postgres_registry.py
      executors/
        __init__.py
        base.py
        function_map_executor.py
        http_executor.py
      policy.py
      cache.py
      audit.py
      utils.py
  examples/
    fastapi_app.py
    cli_demo.py
  migrations/
    001_tool_registry.sql
  pyproject.toml
  README.md
```

## Milestones & Tasks

## M0 — Project Setup (Day 1)
- [ ] Create repository and Python packaging (`pyproject.toml`)
- [ ] Add lint/format (ruff/black) + type checks (mypy optional)
- [ ] Add CI workflow (tests + lint)
- [ ] Add skeleton modules and imports

**Deliverable**
- Bootstrapped repo with CI green

---

## M1 — Core Types + Interfaces (Day 1–2)
### Tasks
- [ ] Define `ToolDef` dataclass (name, description, parameters schema, tags, risk, enabled, namespace)
- [ ] Define `ToolRegistry` interface:
  - `search(tenant_id: str, query: str, k: int) -> list[ToolDef]`
- [ ] Define `ToolExecutor` interface:
  - `can_execute(name)` and `execute(name, args)`

**Deliverable**
- `types.py` and interface stubs with docstrings

---

## M2 — Adapter Core Loop (GPT-5.4-style) (Day 2–3)
### Tasks
- [ ] Implement adapter `run(tenant_id, user_text)`:
  - First LLM call with `tool_search` enabled
  - Detect `tool_search_call` in model output
  - Query registry, build `tool_search_output`, call LLM again
  - Detect `function_call`, parse args JSON
  - Execute tool via executor
  - Send `function_call_output` and return final answer
- [ ] Add safe handling:
  - Invalid JSON arguments → fallback
  - Tool not executable → return safe error text
  - No tool call → return normal answer

**Deliverable**
- `adapter.py` with end-to-end loop

**Acceptance Criteria**
- Unit test: adapter returns final answer with mocked registry/executor
- Unit test: adapter handles no tool_search_call path

---

## M3 — Tool Registry Implementations (Day 3–5)

### M3.1 JSON Registry (quick start)
- [ ] Implement `JsonRegistry` reading `tools.json` (or list in memory)
- [ ] Implement basic text match scoring (BM25-lite heuristic)
- [ ] Add basic filtering (enabled)

**Deliverable**
- `json_registry.py` + example `tools.json`

### M3.2 Postgres Registry (production)
- [ ] Add SQL migration for `tool_registry` table:
  - tenant_id, namespace, name, description, tags, examples
  - parameters_schema JSONB, output_schema JSONB
  - enabled, risk_level, auth_type, endpoint
  - `search_tsv` generated column + GIN index
- [ ] Implement `PostgresRegistry.search()` using `websearch_to_tsquery` + `ts_rank`
- [ ] Add filters:
  - tenant_id, enabled, namespace (optional), max_risk_level, roles (optional)
- [ ] Add connection strategy:
  - psycopg pooling or SQLAlchemy (keep configurable)

**Deliverable**
- `postgres_registry.py` + `migrations/001_tool_registry.sql`

**Acceptance Criteria**
- Integration test runs locally (docker-compose Postgres) and returns tools for a query

---

## M4 — Executors (Day 5–6)

### M4.1 Function Map Executor
- [ ] Map tool name → python handler function
- [ ] Handle exceptions with structured error object

### M4.2 HTTP Executor (optional but common)
- [ ] Execute tool by calling an internal HTTP endpoint
- [ ] Support timeouts, retries, circuit breaker (basic)
- [ ] Support auth (API key / m2m token injection hook)

**Deliverable**
- `function_map_executor.py` + `http_executor.py`

**Acceptance Criteria**
- Unit tests: handler success/failure
- HTTP executor: mocked request tests

---

## M5 — Policy Layer + Safety (Day 6–7)
### Tasks
- [ ] Add policy filtering (in registry or adapter):
  - enabled only
  - risk_level ≤ configured max
  - tenant role access (allowed_roles)
  - environment filtering (prod/stage/dev)
- [ ] Add tool allowlist/denylist per tenant/project
- [ ] Add argument size limits + input validation (basic)
- [ ] Add tool execution timeout enforcement

**Deliverable**
- `policy.py` + config object in adapter init

---

## M6 — Cache + Audit Logging (Day 7–8)
### Tasks
- [ ] Implement TTL cache:
  - cache registry search results by `(tenant_id, query, k, policy_hash)`
- [ ] Add audit logs:
  - tool_search_call query
  - selected tool name
  - execution duration
  - masked arguments (PII masking rules)
- [ ] Add structured logging hooks (pluggable logger)

**Deliverable**
- `cache.py` + `audit.py`

---

## M7 — Examples + Docs (Day 8–9)
### Tasks
- [ ] Add `examples/fastapi_app.py`
  - Endpoint: `/chat` that calls adapter
- [ ] Add `examples/cli_demo.py`
- [ ] README:
  - Quickstart with JSON registry
  - Production setup with Postgres registry
  - How to add a tool
  - How to integrate with OpenAI Responses API
  - Security checklist (risk levels, auth, PII masking)

**Deliverable**
- Working examples + README instructions

---

## M8 — Hardening (Day 9–10)
### Tasks
- [ ] Add regression tests for:
  - tool_search_call → tool_search_output flow
  - function_call args parsing edge cases
  - policy filters
  - caching
- [ ] Load testing guidance:
  - recommended cache TTL
  - parallel tool calls setting
- [ ] Observability:
  - metrics counters (tool calls, errors, latency)

**Deliverable**
- Test suite + minimal metrics

---

## Configuration Contract

### Adapter Config
- `model`: e.g. `gpt-5.4`
- `max_tools`: top-k tools to return
- `max_risk_level`: limit for high-risk tools
- `namespace`: optional constraint for search
- `cache_ttl_seconds`
- `parallel_tool_calls`: default false for deterministic behavior
- `timeout_ms`: tool execution timeout
- `audit_enabled`

---

## Production Readiness Checklist
- [ ] Multi-tenant filtering is mandatory (`tenant_id`)
- [ ] Tool execution is sandboxed or strongly permissioned
- [ ] PII masking in logs
- [ ] Rate limiting per tool and per tenant
- [ ] Timeout + retry strategy for HTTP tools
- [ ] Clear separation between:
  - tool discovery (registry)
  - tool selection (LLM)
  - tool execution (executor)

---

## Acceptance Tests (Definition of Done)

### Functional
- [ ] Given a user request that needs a tool, adapter:
  - triggers tool search,
  - loads the right schema subset,
  - executes the tool,
  - returns a final answer
- [ ] If no tool is needed, returns a normal answer (no tool calls)
- [ ] If tool execution fails, returns a safe error and logs details

### Operational
- [ ] Postgres registry search returns in < 50ms (typical)
- [ ] Cache hit rate measurable and improves latency
- [ ] Logs contain tool selection + durations with masked arguments

---

## Next Iterations (Optional)
- Vector embeddings search for tools (pgvector / Milvus)
- Namespace routing (2-stage search: namespace → tool)
- MCP tool server integration (dynamic discovery)
- Tool schema validation + coercion (Pydantic / jsonschema)
- Multi-step tool calling / parallel tool calls
---
