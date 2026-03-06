# Author: Brad Duy - AI Expert
"""Postgres-backed tool registry using tsvector/GIN full-text search."""

from __future__ import annotations

from typing import Any

from ..types import RiskLevel, ToolDef, ToolRegistry

_SEARCH_SQL = """
SELECT
    name,
    description,
    parameters_schema,
    namespace,
    tags,
    enabled,
    risk_level,
    ts_rank(search_tsv, query) AS rank
FROM tool_registry, websearch_to_tsquery('english', %(query)s) query
WHERE tenant_id = %(tenant_id)s
  AND enabled = true
  AND risk_level <= %(max_risk_level)s
  AND search_tsv @@ query
"""

_NAMESPACE_CLAUSE = "  AND namespace = %(namespace)s"
_ORDER_LIMIT = "
ORDER BY rank DESC
LIMIT %(k)s"


class PostgresRegistry(ToolRegistry):
    """Tool registry backed by PostgreSQL with full-text search.

    Requires the migration in ``migrations/001_tool_registry.sql``.

    Args:
        pool: A psycopg connection pool (``psycopg_pool.AsyncConnectionPool``).
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def search(
        self,
        tenant_id: str,
        query: str,
        k: int = 5,
        *,
        namespace: str | None = None,
        max_risk_level: RiskLevel = RiskLevel.HIGH,
    ) -> list[ToolDef]:
        sql = _SEARCH_SQL
        params: dict[str, Any] = {
            "tenant_id": tenant_id,
            "query": query,
            "max_risk_level": int(max_risk_level),
            "k": k,
        }

        if namespace is not None:
            sql += _NAMESPACE_CLAUSE
            params["namespace"] = namespace

        sql += _ORDER_LIMIT

        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()

        return [self._row_to_tool(row) for row in rows]

    @staticmethod
    def _row_to_tool(row: tuple[Any, ...]) -> ToolDef:
        name, description, parameters_schema, namespace, tags, enabled, risk_level, _rank = row
        return ToolDef(
            name=name,
            description=description,
            parameters=parameters_schema or {},
            namespace=namespace or "",
            tags=tags or [],
            enabled=enabled,
            risk_level=RiskLevel(risk_level),
        )
