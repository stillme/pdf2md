"""Tests for the shared RateLimiter utility."""
from __future__ import annotations

import httpx
import pytest

from pdf2md.providers._ratelimit import (
    RateLimiter,
    is_429,
    is_429_or_529,
    is_connection_error,
)


def _fake_clock_pair():
    """Return ``(ticker, clock, sleep)`` so tests can use a fake clock.

    The clock reads ``ticker[0]``; sleep advances it (and records the
    requested duration so tests can also assert against the call log).
    """
    ticker = [0.0]
    sleeps: list[float] = []

    def clock() -> float:
        return ticker[0]

    def sleep(s: float) -> None:
        sleeps.append(s)
        ticker[0] += s

    return ticker, sleeps, clock, sleep


def test_min_interval_paces_calls():
    ticker, sleeps, clock, sleep = _fake_clock_pair()
    limiter = RateLimiter(min_interval_s=2.0, clock=clock, sleep=sleep)

    timestamps: list[float] = []

    def fn() -> str:
        timestamps.append(clock())
        return "ok"

    limiter.call(fn)
    limiter.call(fn)

    # First call needs no wait; second must observe at least min_interval_s
    # of clock advancement (via the injected sleep).
    assert timestamps[0] == 0.0
    assert timestamps[1] - timestamps[0] >= 2.0
    assert sleeps == [2.0]


def test_retry_on_predicate():
    ticker, sleeps, clock, sleep = _fake_clock_pair()
    attempts = {"n": 0}

    def fn() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("transient")
        return "done"

    limiter = RateLimiter(
        max_retries=3,
        retry_on=lambda e: isinstance(e, RuntimeError),
        initial_backoff_s=1.0,
        backoff_multiplier=2.0,
        clock=clock,
        sleep=sleep,
    )

    assert limiter.call(fn) == "done"
    assert attempts["n"] == 3
    # Two retries → backoffs of 1 then 2 seconds.
    assert sleeps == [1.0, 2.0]


def test_retry_exhausted_reraises():
    ticker, sleeps, clock, sleep = _fake_clock_pair()
    attempts = {"n": 0}

    def fn() -> str:
        attempts["n"] += 1
        raise RuntimeError("always fails")

    limiter = RateLimiter(
        max_retries=2,
        retry_on=lambda e: isinstance(e, RuntimeError),
        initial_backoff_s=1.0,
        backoff_multiplier=2.0,
        clock=clock,
        sleep=sleep,
    )

    with pytest.raises(RuntimeError, match="always fails"):
        limiter.call(fn)
    # Initial attempt + max_retries retries = 3 invocations.
    assert attempts["n"] == 3
    # Two retry sleeps occurred before re-raising.
    assert sleeps == [1.0, 2.0]


def test_retry_predicate_false_reraises_immediately():
    ticker, sleeps, clock, sleep = _fake_clock_pair()
    attempts = {"n": 0}

    def fn() -> str:
        attempts["n"] += 1
        raise ValueError("nope")

    limiter = RateLimiter(
        max_retries=5,
        retry_on=lambda e: isinstance(e, RuntimeError),
        clock=clock,
        sleep=sleep,
    )

    with pytest.raises(ValueError, match="nope"):
        limiter.call(fn)
    assert attempts["n"] == 1
    assert sleeps == []


def test_backoff_grows_exponentially():
    ticker, sleeps, clock, sleep = _fake_clock_pair()

    def fn() -> str:
        raise RuntimeError("x")

    limiter = RateLimiter(
        max_retries=3,
        retry_on=lambda e: True,
        initial_backoff_s=1.0,
        backoff_multiplier=2.0,
        clock=clock,
        sleep=sleep,
    )

    with pytest.raises(RuntimeError):
        limiter.call(fn)

    assert sleeps == [1.0, 2.0, 4.0]


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.invalid/")
    response = httpx.Response(status_code=status, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


def test_is_429_predicate():
    assert is_429(_http_error(429)) is True
    assert is_429(_http_error(200)) is False
    assert is_429(_http_error(500)) is False
    assert is_429(RuntimeError("not http")) is False


def test_is_429_or_529_predicate():
    assert is_429_or_529(_http_error(429)) is True
    assert is_429_or_529(_http_error(529)) is True
    assert is_429_or_529(_http_error(500)) is False
    assert is_429_or_529(_http_error(200)) is False


def test_is_connection_error_predicate():
    request = httpx.Request("POST", "https://example.invalid/")
    assert is_connection_error(httpx.ConnectError("nope", request=request)) is True
    assert is_connection_error(_http_error(429)) is False
    assert is_connection_error(RuntimeError("x")) is False
