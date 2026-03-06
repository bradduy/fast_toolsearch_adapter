# Author: Brad Duy - AI Expert
"""JSON-file backed tool registry with BM25-lite scoring."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from ..types import RiskLevel, ToolDef, ToolRegistry


def _tokenize(text: str) -> list[str]:
    """Lowercase tokenizer splitting on non-alphanumeric chars."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _idf(term: str, docs: list[list[str]]) -> float:
    """Inverse document frequency."""
    df = sum(1 for doc in docs if term in doc)
    if df == 0:
        return 0.0
    return math.log((len(docs) - df + 0.5) / (df + 0.5) + 1.0)


def _bm25_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    all_docs: list[list[str]],
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """BM25 scoring for a single document against a query."""
    if not doc_tokens:
        return 0.0
    avg_dl = sum(len(d) for d in all_docs) / max(len(all_docs), 1)
    dl = len(doc_tokens)
    score = 0.0
    for term in query_tokens:
        tf = doc_tokens.count(term)
        idf = _idf(term, all_docs)
        numerator = tf * (k1 + 1)
        denominator = tf + k1 * (1 - b + b * dl / max(avg_dl, 1))
        score += idf * numerator / denominator
    return score


def _tool_from_dict(data: dict[str, Any]) -> ToolDef:
    """Parse a ToolDef from a dict (e.g. loaded from JSON)."""
    risk = data.get("risk_level", 1)
    if isinstance(risk, str):
        risk = RiskLevel[risk.upper()]
    else:
        risk = RiskLevel(risk)
    return ToolDef(
        name=data["name"],
        description=data.get("description", ""),
        parameters=data.get("parameters", {}),
        namespace=data.get("namespace", ""),
        tags=data.get("tags", []),
        enabled=data.get("enabled", True),
        risk_level=risk,
    )


class JsonRegistry(ToolRegistry):
    """Tool registry backed by an in-memory list or a JSON file.

    Implements BM25-lite scoring over tool name + description + tags.
    """

    def __init__(
        self,
        tools: list[ToolDef] | None = None,
        path: str | Path | None = None,
    ) -> None:
        if tools is not None:
            self._tools = list(tools)
        elif path is not None:
            raw = json.loads(Path(path).read_text())
            self._tools = [_tool_from_dict(t) for t in raw]
        else:
            self._tools = []

        # Pre-tokenize docs for BM25
        self._doc_tokens: list[list[str]] = [self._tool_text(t) for t in self._tools]

    @staticmethod
    def _tool_text(tool: ToolDef) -> list[str]:
        parts = f"{tool.name} {tool.description} {' '.join(tool.tags)}"
        return _tokenize(parts)

    async def search(
        self,
        tenant_id: str,
        query: str,
        k: int = 5,
        *,
        namespace: str | None = None,
        max_risk_level: RiskLevel = RiskLevel.HIGH,
    ) -> list[ToolDef]:
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scored: list[tuple[float, ToolDef]] = []
        for i, tool in enumerate(self._tools):
            if not tool.enabled:
                continue
            if tool.risk_level > max_risk_level:
                continue
            if namespace is not None and tool.namespace != namespace:
                continue
            score = _bm25_score(query_tokens, self._doc_tokens[i], self._doc_tokens)
            if score > 0:
                scored.append((score, tool))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:k]]
