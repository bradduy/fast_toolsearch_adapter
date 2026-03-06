# Author: Brad Duy - AI Expert
"""Tests for policy filtering."""

from __future__ import annotations

import pytest

from toolsearch_adapter import RiskLevel, ToolDef
from toolsearch_adapter.policy import PolicyConfig, PolicyFilter


@pytest.fixture
def tools():
    return [
        ToolDef(
            name="safe_tool",
            description="A safe tool",
            parameters={},
            risk_level=RiskLevel.LOW,
            enabled=True,
        ),
        ToolDef(
            name="risky_tool",
            description="A risky tool",
            parameters={},
            risk_level=RiskLevel.CRITICAL,
            enabled=True,
        ),
        ToolDef(
            name="disabled_tool",
            description="A disabled tool",
            parameters={},
            risk_level=RiskLevel.LOW,
            enabled=False,
        ),
        ToolDef(
            name="medium_tool",
            description="A medium-risk tool",
            parameters={},
            risk_level=RiskLevel.MEDIUM,
            enabled=True,
            namespace="internal",
        ),
    ]


class TestPolicyFilter:
    def test_default_policy_filters_disabled(self, tools):
        pf = PolicyFilter(PolicyConfig())
        result = pf.filter(tools)
        names = [t.name for t in result]
        assert "disabled_tool" not in names
        assert "safe_tool" in names

    def test_risk_level_filter(self, tools):
        pf = PolicyFilter(PolicyConfig(max_risk_level=RiskLevel.MEDIUM))
        result = pf.filter(tools)
        names = [t.name for t in result]
        assert "risky_tool" not in names
        assert "safe_tool" in names
        assert "medium_tool" in names

    def test_denylist(self, tools):
        pf = PolicyFilter(PolicyConfig(denylist={"safe_tool"}))
        result = pf.filter(tools)
        names = [t.name for t in result]
        assert "safe_tool" not in names

    def test_allowlist(self, tools):
        pf = PolicyFilter(PolicyConfig(allowlist={"safe_tool", "medium_tool"}))
        result = pf.filter(tools)
        names = [t.name for t in result]
        assert "risky_tool" not in names
        assert "safe_tool" in names

    def test_namespace_filter(self, tools):
        pf = PolicyFilter(PolicyConfig(allowed_namespaces=["internal"]))
        result = pf.filter(tools)
        names = [t.name for t in result]
        assert "safe_tool" not in names
        assert "medium_tool" in names

    def test_denied_namespace(self, tools):
        pf = PolicyFilter(PolicyConfig(denied_namespaces=["internal"]))
        result = pf.filter(tools)
        names = [t.name for t in result]
        assert "medium_tool" not in names
        assert "safe_tool" in names
