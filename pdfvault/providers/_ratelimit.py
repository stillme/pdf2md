"""Shared rate-limiting + retry/backoff utility for VLM providers.

Wraps a callable with two protections:

1. Pacing: enforce a minimum interval between successful calls
   (per-provider RPM limit).
2. Retry/backoff: catch matching exceptions, sleep with exponential
   backoff, retry up to ``max_retries``.

Clock and sleep are injectable so tests don't actually wait.
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

import httpx

T = TypeVar("T")


def is_429(exc: BaseException) -> bool:
    """True if exc is an httpx HTTP 429 (Too Many Requests) response error."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429
    return False


def is_429_or_529(exc: BaseException) -> bool:
    """True for HTTP 429 (rate limit) or 529 (Anthropic overloaded)."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 529)
    return False


def is_connection_error(exc: BaseException) -> bool:
    """True if exc is a transport-level httpx connection error.

    Used by the Ollama provider to retry transient local-server hiccups
    (e.g. process briefly unreachable on cold start).
    """
    return isinstance(exc, httpx.RequestError)


class RateLimiter:
    """Pace + retry wrapper around a parameterless callable.

    ``min_interval_s`` enforces a minimum gap between *successful* calls.
    ``retry_on(exc)`` decides whether a raised exception triggers retry;
    on retry the limiter sleeps ``initial_backoff_s * multiplier**attempt``
    seconds before the next attempt. After ``max_retries`` consecutive
    failures the final exception is re-raised.
    """

    def __init__(
        self,
        *,
        min_interval_s: float = 0.0,
        max_retries: int = 3,
        initial_backoff_s: float = 1.0,
        backoff_multiplier: float = 2.0,
        retry_on: Callable[[BaseException], bool] = lambda e: False,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_interval_s = min_interval_s
        self._max_retries = max_retries
        self._initial_backoff_s = initial_backoff_s
        self._backoff_multiplier = backoff_multiplier
        self._retry_on = retry_on
        self._clock = clock
        self._sleep = sleep
        self._last_call: float | None = None

    def _wait_for_interval(self) -> None:
        if self._min_interval_s <= 0 or self._last_call is None:
            return
        elapsed = self._clock() - self._last_call
        if elapsed < self._min_interval_s:
            self._sleep(self._min_interval_s - elapsed)

    def call(self, fn: Callable[[], T]) -> T:
        """Invoke fn() respecting min_interval_s pacing and retry_on policy."""
        attempt = 0
        while True:
            self._wait_for_interval()
            try:
                result = fn()
            except BaseException as exc:
                if attempt < self._max_retries and self._retry_on(exc):
                    backoff = self._initial_backoff_s * (
                        self._backoff_multiplier ** attempt
                    )
                    self._sleep(backoff)
                    # Reset pacing window — we already waited, and the
                    # remote side just told us we were too fast.
                    self._last_call = self._clock()
                    attempt += 1
                    continue
                raise
            self._last_call = self._clock()
            return result
