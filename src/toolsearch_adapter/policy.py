# Author: Brad Duy - AI Expert
"""Policy layer for filtering tools by tenant, risk, and access rules."""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import RiskLevel, ToolDef


@dataclass(slots=True)
class PolicyConfig:
    """Policy configuration for tool filtering."""

    max_risk_level: RiskLevel = RiskLevel.HIGH
    allowed_namespaces: list[str] | None = None
    denied_namespaces: list[str] | None = None
    allowlist: set[str] | None = None  # tool names explicitly allowed
    denylist: set[str] = field(default_factory=set)  # tool names explicitly denied
    require_enabled: bool = True


class PolicyFilter:
    """Applies policy rules to filter tool search results."""

    def __init__(self, config: PolicyConfig | None = None) -> None:
        self._config = config or PolicyConfig()

    @property
    def config(self) -> PolicyConfig:
        return self._config

    def filter(self, tools: list[ToolDef]) -> list[ToolDef]:
        """Apply all policy rules and return only permitted tools."""
        return [t for t in tools if self._is_allowed(t)]

    def _is_allowed(self, tool: ToolDef) -> bool:
        cfg = self._config

        if cfg.require_enabled and not tool.enabled:
            return False

        if tool.risk_level > cfg.max_risk_level:
            return False

        if tool.name in cfg.denylist:
            return False

        if cfg.allowlist is not None and tool.name not in cfg.allowlist:
            return False

        if cfg.allowed_namespaces is not None:
            if tool.namespace not in cfg.allowed_namespaces:
                return False

        if cfg.denied_namespaces is not None:
            if tool.namespace in cfg.denied_namespaces:
                return False

        return True
