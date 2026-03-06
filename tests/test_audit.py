# Author: Brad Duy - AI Expert
"""Tests for audit logging."""

from __future__ import annotations

from toolsearch_adapter.audit import AuditLogger, default_mask


class TestDefaultMask:
    def test_masks_password(self):
        result = default_mask({"username": "alice", "password": "secret123"})
        assert result["username"] == "alice"
        assert result["password"] == "***MASKED***"

    def test_masks_api_key(self):
        result = default_mask({"api_key": "sk-12345", "city": "London"})
        assert result["api_key"] == "***MASKED***"
        assert result["city"] == "London"

    def test_masks_nested(self):
        result = default_mask({"auth": {"token": "abc", "user": "bob"}})
        assert result["auth"]["token"] == "***MASKED***"
        assert result["auth"]["user"] == "bob"

    def test_no_sensitive_keys(self):
        data = {"city": "London", "count": 5}
        result = default_mask(data)
        assert result == data


class TestAuditLogger:
    def test_log_search(self):
        logger = AuditLogger(enabled=True)
        logger.log_search("t1", "weather", 3, 12.5)
        assert len(logger.entries) == 1
        assert logger.entries[0].event == "tool_search"
        assert logger.entries[0].query == "weather"

    def test_log_execution(self):
        logger = AuditLogger(enabled=True)
        logger.log_execution("t1", "get_weather", {"city": "London"}, 50.0)
        assert len(logger.entries) == 1
        assert logger.entries[0].event == "tool_execution"
        assert logger.entries[0].tool_name == "get_weather"

    def test_disabled_logger(self):
        logger = AuditLogger(enabled=False)
        logger.log_search("t1", "weather", 3, 12.5)
        logger.log_execution("t1", "get_weather", {"city": "London"}, 50.0)
        assert len(logger.entries) == 0

    def test_execution_masks_sensitive_args(self):
        logger = AuditLogger(enabled=True)
        logger.log_execution("t1", "login", {"username": "alice", "password": "s3cret"}, 10.0)
        entry = logger.entries[0]
        assert entry.arguments["password"] == "***MASKED***"
        assert entry.arguments["username"] == "alice"

    def test_custom_mask_hook(self):
        def custom_mask(args):
            return {k: "REDACTED" for k in args}

        logger = AuditLogger(enabled=True, mask_hook=custom_mask)
        logger.log_execution("t1", "tool", {"x": 1, "y": 2}, 5.0)
        entry = logger.entries[0]
        assert all(v == "REDACTED" for v in entry.arguments.values())
