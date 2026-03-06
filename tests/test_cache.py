# Author: Brad Duy - AI Expert
"""Tests for TTL cache."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from toolsearch_adapter import RiskLevel, ToolDef
from toolsearch_adapter.cache import TTLCache


@pytest.fixture
def sample_tools():
    return [
        ToolDef(
            name="get_weather",
            description="Weather tool",
            parameters={},
            risk_level=RiskLevel.LOW,
        ),
    ]


class TestTTLCache:
    def test_cache_hit(self, sample_tools):
        cache = TTLCache(ttl_seconds=60)
        cache.put("t1", "weather", 5, sample_tools)

        result = cache.get("t1", "weather", 5)
        assert result is not None
        assert len(result) == 1
        assert result[0].name == "get_weather"

    def test_cache_miss(self):
        cache = TTLCache(ttl_seconds=60)
        result = cache.get("t1", "nonexistent", 5)
        assert result is None

    def test_cache_expiry(self, sample_tools):
        cache = TTLCache(ttl_seconds=1)
        cache.put("t1", "weather", 5, sample_tools)

        # Simulate time passing
        with patch("toolsearch_adapter.cache.time") as mock_time:
            mock_time.monotonic.side_effect = [
                # First call in put already happened
                # get calls monotonic once
                time.monotonic() + 2,  # expired
            ]
            # Re-create to use fresh mock
            pass

        # Direct test: sleep briefly and check with tiny TTL
        cache2 = TTLCache(ttl_seconds=0)
        cache2.put("t1", "weather", 5, sample_tools)
        # With TTL=0, next get should be expired
        time.sleep(0.01)
        result = cache2.get("t1", "weather", 5)
        assert result is None

    def test_cache_different_keys(self, sample_tools):
        cache = TTLCache(ttl_seconds=60)
        cache.put("t1", "weather", 5, sample_tools)

        # Different tenant
        assert cache.get("t2", "weather", 5) is None
        # Different query
        assert cache.get("t1", "math", 5) is None
        # Different k
        assert cache.get("t1", "weather", 10) is None

    def test_invalidate(self, sample_tools):
        cache = TTLCache(ttl_seconds=60)
        cache.put("t1", "weather", 5, sample_tools)
        assert cache.size == 1

        cache.invalidate()
        assert cache.size == 0
        assert cache.get("t1", "weather", 5) is None

    def test_cache_with_namespace(self, sample_tools):
        cache = TTLCache(ttl_seconds=60)
        cache.put("t1", "weather", 5, sample_tools, namespace="prod")

        # Without namespace -> miss
        assert cache.get("t1", "weather", 5) is None
        # With matching namespace -> hit
        assert cache.get("t1", "weather", 5, namespace="prod") is not None
