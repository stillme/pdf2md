"""Tests for the Claude CLI provider.

The provider shells out to the ``claude`` binary, so every test mocks
``subprocess.run`` and ``shutil.which`` — none of these tests start a
real subprocess or touch the user's subscription quota.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from pdf2md.providers.claude_cli import (
    ClaudeCLIProvider,
    ClaudeCLIRateLimitError,
)


# ---------------------------------------------------------------------------
# Helpers — build a fake stream-json transcript
# ---------------------------------------------------------------------------


def _result_event(text: str = "ok", *, is_error: bool = False) -> str:
    return json.dumps({
        "type": "result",
        "subtype": "success" if not is_error else "error",
        "is_error": is_error,
        "result": text,
        "duration_ms": 1234,
        "duration_api_ms": 1100,
        "num_turns": 1,
        "session_id": "test-session",
        "total_cost_usd": 0.01,
        "usage": {
            "input_tokens": 10,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "output_tokens": 5,
        },
    })


def _rate_limit_event(status: str, resets_at: int = 0, kind: str = "five_hour") -> str:
    return json.dumps({
        "type": "rate_limit_event",
        "rate_limit_info": {
            "status": status,
            "resetsAt": resets_at,
            "rateLimitType": kind,
        },
    })


class _FakeProc:
    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------


def test_returns_result_text_from_stream_json():
    provider = ClaudeCLIProvider(model="sonnet")
    stdout = "\n".join([
        _rate_limit_event("allowed"),
        _result_event("hello world"),
    ])
    with (
        patch("pdf2md.providers.claude_cli.shutil.which", return_value="/usr/bin/claude"),
        patch(
            "pdf2md.providers.claude_cli.subprocess.run",
            return_value=_FakeProc(stdout=stdout),
        ),
    ):
        out = provider.complete_sync("describe", image=None)
    assert out == "hello world"


def test_raises_when_cli_returns_nonzero():
    provider = ClaudeCLIProvider(model="sonnet")
    with (
        patch("pdf2md.providers.claude_cli.shutil.which", return_value="/usr/bin/claude"),
        patch(
            "pdf2md.providers.claude_cli.subprocess.run",
            return_value=_FakeProc(stdout="", stderr="boom", returncode=2),
        ),
    ):
        with pytest.raises(RuntimeError, match="claude exit 2"):
            provider.complete_sync("anything")


def test_raises_when_no_result_event_present():
    """Truncated transcripts must fail loudly, not silently return ''."""
    provider = ClaudeCLIProvider(model="sonnet")
    stdout = _rate_limit_event("allowed")  # no result line
    with (
        patch("pdf2md.providers.claude_cli.shutil.which", return_value="/usr/bin/claude"),
        patch(
            "pdf2md.providers.claude_cli.subprocess.run",
            return_value=_FakeProc(stdout=stdout),
        ),
    ):
        with pytest.raises(RuntimeError, match="no result event"):
            provider.complete_sync("anything")


def test_propagates_error_result():
    provider = ClaudeCLIProvider(model="sonnet")
    stdout = _result_event("server unavailable", is_error=True)
    with (
        patch("pdf2md.providers.claude_cli.shutil.which", return_value="/usr/bin/claude"),
        patch(
            "pdf2md.providers.claude_cli.subprocess.run",
            return_value=_FakeProc(stdout=stdout),
        ),
    ):
        with pytest.raises(RuntimeError, match="claude reported error"):
            provider.complete_sync("anything")


# ---------------------------------------------------------------------------
# Rate-limit handling
# ---------------------------------------------------------------------------


def test_raises_rate_limit_error_on_blocked_event():
    """When the CLI signals a non-allowed status, surface the reset time
    so the caller can decide how long to back off."""
    provider = ClaudeCLIProvider(model="sonnet")
    # Short-circuit the limiter's bound sleep — the default arg captured
    # ``time.sleep`` at module-import time, so patching ``time.sleep``
    # later has no effect on this instance.
    provider._limiter._sleep = lambda _: None
    stdout = "\n".join([
        _rate_limit_event("denied", resets_at=1900000000, kind="five_hour"),
        _result_event("(should be ignored)"),
    ])
    with (
        patch("pdf2md.providers.claude_cli.shutil.which", return_value="/usr/bin/claude"),
        patch(
            "pdf2md.providers.claude_cli.subprocess.run",
            return_value=_FakeProc(stdout=stdout),
        ),
    ):
        with pytest.raises(ClaudeCLIRateLimitError) as excinfo:
            provider.complete_sync("anything")
    assert excinfo.value.reset_at == 1900000000
    assert excinfo.value.rate_limit_type == "five_hour"


def test_allowed_status_does_not_block():
    provider = ClaudeCLIProvider(model="sonnet")
    stdout = "\n".join([
        _rate_limit_event("allowed", resets_at=1900000000),
        _result_event("ok"),
    ])
    with (
        patch("pdf2md.providers.claude_cli.shutil.which", return_value="/usr/bin/claude"),
        patch(
            "pdf2md.providers.claude_cli.subprocess.run",
            return_value=_FakeProc(stdout=stdout),
        ),
    ):
        assert provider.complete_sync("anything") == "ok"


# ---------------------------------------------------------------------------
# Message construction
# ---------------------------------------------------------------------------


def test_image_payload_uses_base64_with_mime_type():
    """When an image is supplied it must be embedded as base64 in the
    user message — that's what skips the slow Read-tool roundtrip."""
    provider = ClaudeCLIProvider(model="sonnet")
    captured: dict[str, object] = {}

    def fake_run(*args, **kwargs):
        captured["input"] = kwargs.get("input", "")
        return _FakeProc(stdout=_result_event("ok"))

    # PNG magic bytes so detect_image_mime returns "image/png".
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

    with (
        patch("pdf2md.providers.claude_cli.shutil.which", return_value="/usr/bin/claude"),
        patch("pdf2md.providers.claude_cli.subprocess.run", side_effect=fake_run),
    ):
        provider.complete_sync("describe", image=png_bytes)

    payload = json.loads(captured["input"].strip())
    parts = payload["message"]["content"]
    assert any(p.get("type") == "image" for p in parts)
    image_part = next(p for p in parts if p["type"] == "image")
    assert image_part["source"]["type"] == "base64"
    assert image_part["source"]["media_type"] == "image/png"
    text_part = next(p for p in parts if p["type"] == "text")
    assert text_part["text"] == "describe"


def test_no_image_sends_text_only_payload():
    provider = ClaudeCLIProvider(model="sonnet")
    captured: dict[str, object] = {}

    def fake_run(*args, **kwargs):
        captured["input"] = kwargs.get("input", "")
        return _FakeProc(stdout=_result_event("ok"))

    with (
        patch("pdf2md.providers.claude_cli.shutil.which", return_value="/usr/bin/claude"),
        patch("pdf2md.providers.claude_cli.subprocess.run", side_effect=fake_run),
    ):
        provider.complete_sync("just text")

    payload = json.loads(captured["input"].strip())
    parts = payload["message"]["content"]
    assert all(p.get("type") != "image" for p in parts)


# ---------------------------------------------------------------------------
# Subprocess invocation
# ---------------------------------------------------------------------------


def test_invocation_passes_required_flags():
    """We rely on a specific flag set for speed (stream-json IO, tools
    disabled, single turn). Drift here will silently re-introduce the
    19s/call regression — pin the contract with a test."""
    provider = ClaudeCLIProvider(model="sonnet")
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = list(cmd)
        return _FakeProc(stdout=_result_event("ok"))

    with (
        patch("pdf2md.providers.claude_cli.shutil.which", return_value="/usr/bin/claude"),
        patch("pdf2md.providers.claude_cli.subprocess.run", side_effect=fake_run),
    ):
        provider.complete_sync("anything")

    cmd = captured["cmd"]
    assert cmd[0] == "claude"
    assert "--print" in cmd
    assert "--input-format" in cmd and "stream-json" in cmd
    assert "--output-format" in cmd and "stream-json" in cmd
    assert "--verbose" in cmd
    assert "--max-turns" in cmd and "1" in cmd
    assert "--tools" in cmd
    # An empty --tools value disables every tool, which is what skips
    # the Read-tool roundtrip on image inputs.
    tools_idx = cmd.index("--tools")
    assert cmd[tools_idx + 1] == ""


def test_raises_when_claude_binary_is_missing():
    provider = ClaudeCLIProvider(model="sonnet")
    with patch("pdf2md.providers.claude_cli.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="Claude CLI not found"):
            provider.complete_sync("anything")


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


def test_registry_returns_claude_cli_provider_for_explicit_string():
    from pdf2md.providers.registry import get_provider

    provider = get_provider("claude-cli")
    assert isinstance(provider, ClaudeCLIProvider)
    assert provider.name == "claude-cli"


def test_registry_accepts_name_with_underscore_alias():
    """``claude-cli`` and ``claude_cli`` both resolve — accept whichever
    feels natural in shell or Python contexts."""
    from pdf2md.providers.registry import get_provider

    provider = get_provider("claude_cli/sonnet")
    assert isinstance(provider, ClaudeCLIProvider)


def test_detect_providers_lists_claude_cli_with_binary_presence():
    from pdf2md.providers.registry import detect_providers

    with patch("shutil.which", return_value="/usr/bin/claude"):
        entries = detect_providers()
    cli_entry = next(e for e in entries if e["name"] == "claude-cli")
    assert cli_entry["available"] is True
    assert cli_entry["env_var"] is None


def test_detect_providers_marks_claude_cli_unavailable_when_missing():
    from pdf2md.providers.registry import detect_providers

    with patch("shutil.which", return_value=None):
        entries = detect_providers()
    cli_entry = next(e for e in entries if e["name"] == "claude-cli")
    assert cli_entry["available"] is False
