"""Claude CLI provider — leverages a local Claude Max / Pro / Team subscription.

Spawns the ``claude`` binary with ``--print --input-format stream-json
--output-format stream-json`` and a single user message that embeds the
prompt + (optionally) a base64 image. The CLI authenticates via OAuth
against the user's subscription, so calls don't bill the API key — they
draw from the subscription's per-window message budget instead.

Designed for batch use: each call is a single subprocess that returns
quickly enough (~5s with cache miss, ~3s with a warm cache) to be
sequenced through the standard provider rate limiter. The system prompt
is intentionally minimal to keep the cache footprint low.

When the CLI emits a ``rate_limit_event`` whose status isn't ``allowed``
we raise a ``ClaudeCLIRateLimitError`` carrying the reset timestamp; the
``RateLimiter`` retries with a backoff long enough to clear the window.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time

from pdf2md.cache import cached_call
from pdf2md.providers._ratelimit import RateLimiter


class ClaudeCLIRateLimitError(RuntimeError):
    """Raised when the Claude CLI signals a subscription rate-limit hit.

    Carries ``reset_at`` (unix timestamp, seconds) and
    ``rate_limit_type`` (e.g. ``"five_hour"``) so the caller can decide
    how long to sleep before retrying.
    """

    def __init__(self, reset_at: int, rate_limit_type: str) -> None:
        super().__init__(
            f"Claude CLI rate limit hit ({rate_limit_type}); "
            f"resets at unix={reset_at}"
        )
        self.reset_at = reset_at
        self.rate_limit_type = rate_limit_type


def _is_cli_rate_limit(exc: BaseException) -> bool:
    return isinstance(exc, ClaudeCLIRateLimitError)


# Minimal system prompt. Each token here is paid for in cache_creation
# tokens on the first call of a 5-minute window — keep it tight. The CLI
# still injects its own internals around this string but they cache too.
_DEFAULT_SYSTEM_PROMPT = (
    "You are a precise vision/document assistant. Follow instructions "
    "exactly. When asked to return JSON, return ONLY valid JSON with "
    "no surrounding prose."
)


class ClaudeCLIProvider:
    """VLM provider that delegates each call to a local ``claude`` CLI process.

    Auth piggybacks on the user's logged-in CLI session (run ``claude /login``
    once), so calls are billed against the subscription rather than an
    API key. There is no automatic fallback to the API.

    Default model is ``haiku`` because the dominant batch workload is
    figure description and table cleanup — Haiku handles both reliably
    at ~3x the throughput of Sonnet on the same subscription. Pick
    ``provider="claude-cli/sonnet"`` (or ``opus``) when accuracy on a
    specific paper matters more than batch speed.
    """

    _DEFAULT_MODEL = "haiku"

    def __init__(
        self,
        model: str | None = None,
        *,
        system_prompt: str | None = None,
        timeout_s: float = 300.0,
    ) -> None:
        self._model = model or self._DEFAULT_MODEL
        self._system_prompt = system_prompt or _DEFAULT_SYSTEM_PROMPT
        self._timeout_s = timeout_s
        # Pacing default: 1.5s between calls leaves headroom under Max
        # subscription windows; override with CLAUDE_CLI_MIN_INTERVAL_S.
        # On a rate-limit event we sleep until the window resets, so this
        # only governs friendly steady-state pacing.
        min_interval = float(
            os.environ.get("CLAUDE_CLI_MIN_INTERVAL_S", "1.5")
        )
        # Long backoff because rate-limit windows are 5 hours wide;
        # actual sleep length is computed from the event payload below.
        self._limiter = RateLimiter(
            min_interval_s=min_interval,
            max_retries=2,
            initial_backoff_s=5.0,
            backoff_multiplier=2.0,
            retry_on=_is_cli_rate_limit,
        )

    @property
    def name(self) -> str:
        return "claude-cli"

    # --- public ----------------------------------------------------------

    def complete_sync(self, prompt: str, image: bytes | None = None) -> str:
        return cached_call(
            lambda: self._limiter.call(lambda: self._invoke(prompt, image)),
            prompt=prompt, model=self._model, image=image, provider=self.name,
        )

    async def complete(self, prompt: str, image: bytes | None = None) -> str:
        return self.complete_sync(prompt, image)

    # --- internals -------------------------------------------------------

    def _invoke(self, prompt: str, image: bytes | None) -> str:
        if shutil.which("claude") is None:
            raise RuntimeError(
                "Claude CLI not found on PATH. Install it from "
                "https://docs.claude.com/en/docs/claude-code/setup and run "
                "`claude /login` to authenticate."
            )
        stdin_data = self._build_message(prompt, image)
        cmd = [
            "claude", "--print",
            "--model", self._model,
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--system-prompt", self._system_prompt,
            "--max-turns", "1",
            "--tools", "",
            "--no-session-persistence",
        ]
        proc = subprocess.run(
            cmd,
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=self._timeout_s,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"claude exit {proc.returncode}: "
                f"{(proc.stderr or '')[:500]}"
            )
        return self._parse_output(proc.stdout)

    def _build_message(self, prompt: str, image: bytes | None) -> str:
        content: list[dict] = []
        if image is not None:
            from pdf2md.providers.base import detect_image_mime
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": detect_image_mime(image),
                    "data": base64.b64encode(image).decode("ascii"),
                },
            })
        content.append({"type": "text", "text": prompt})
        msg = {
            "type": "user",
            "message": {"role": "user", "content": content},
        }
        return json.dumps(msg) + "\n"

    def _parse_output(self, stdout: str) -> str:
        """Extract the assistant's text from a stream-json transcript.

        Walks every event line. A ``rate_limit_event`` whose status is
        not ``allowed`` raises immediately (so the limiter can back off
        until the window resets). The terminal ``result`` event carries
        the final text — both success and error variants live there.
        """
        last_result: dict | None = None
        for raw_line in stdout.split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event.get("type") == "rate_limit_event":
                info = event.get("rate_limit_info") or {}
                if info.get("status") not in (None, "allowed"):
                    raise ClaudeCLIRateLimitError(
                        reset_at=int(info.get("resetsAt") or 0),
                        rate_limit_type=str(info.get("rateLimitType") or "unknown"),
                    )
                continue

            if event.get("type") == "result":
                last_result = event

        if last_result is None:
            raise RuntimeError(
                f"no result event in claude output: {stdout[-500:]!r}"
            )
        if last_result.get("is_error"):
            raise RuntimeError(
                f"claude reported error: {last_result.get('result', '')[:500]!r}"
            )
        return str(last_result.get("result") or "")
