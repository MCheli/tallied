"""Tests for the in-memory sliding-window rate limiter."""

import time

import pytest
from fastapi import HTTPException

from app.middleware.rate_limit import RateLimiter


def test_allows_requests_within_limit():
    limiter = RateLimiter(requests_per_hour=5)
    for _ in range(5):
        limiter.check("test-key")  # should not raise


def test_rejects_when_limit_exceeded():
    limiter = RateLimiter(requests_per_hour=3)
    for _ in range(3):
        limiter.check("test-key")

    with pytest.raises(HTTPException) as exc_info:
        limiter.check("test-key")

    assert exc_info.value.status_code == 429
    assert "Rate limit exceeded" in exc_info.value.detail


def test_different_keys_are_independent():
    limiter = RateLimiter(requests_per_hour=2)
    limiter.check("key-a")
    limiter.check("key-a")

    # key-a is exhausted
    with pytest.raises(HTTPException):
        limiter.check("key-a")

    # key-b still has quota
    limiter.check("key-b")


def test_get_usage_returns_correct_values():
    limiter = RateLimiter(requests_per_hour=100)
    limiter.check("usage-key")
    limiter.check("usage-key")
    limiter.check("usage-key")

    limit, remaining, reset_ts = limiter.get_usage("usage-key")
    assert limit == 100
    assert remaining == 97
    assert reset_ts > int(time.time())


def test_get_usage_for_unknown_key():
    limiter = RateLimiter(requests_per_hour=100)
    limit, remaining, reset_ts = limiter.get_usage("never-seen")
    assert limit == 100
    assert remaining == 100


def test_expired_requests_are_pruned():
    limiter = RateLimiter(requests_per_hour=2)
    # Manually insert old timestamps
    old_time = time.time() - 7200  # 2 hours ago
    limiter._requests["prune-key"] = [old_time, old_time + 1]

    # These old entries should be pruned, allowing new requests
    limiter.check("prune-key")  # should not raise

    limit, remaining, _ = limiter.get_usage("prune-key")
    assert remaining == 1  # only the new request counts
