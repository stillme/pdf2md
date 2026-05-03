"""Tests for the content-addressed VLM response cache."""
from __future__ import annotations
from pathlib import Path

from pdfvault.cache import cache_key, cached_call


class _FakeProvider:
    def __init__(self, response: str = "hello"):
        self.calls = 0
        self.response = response

    def complete_sync(self, prompt: str, image: bytes | None = None) -> str:
        def _call() -> str:
            self.calls += 1
            return self.response

        return cached_call(
            _call, prompt=prompt, model="fake-model", image=image, provider="fake",
        )


def test_cache_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("PDFVAULT_CACHE", raising=False)
    monkeypatch.setenv("PDFVAULT_CACHE_DIR", str(tmp_path))
    p = _FakeProvider()
    p.complete_sync("hi")
    p.complete_sync("hi")
    assert p.calls == 2
    written = list(tmp_path.rglob("*.txt"))
    assert written == []


def test_cache_hit_returns_value_without_calling_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("PDFVAULT_CACHE", "1")
    monkeypatch.setenv("PDFVAULT_CACHE_DIR", str(tmp_path))
    p = _FakeProvider(response="cached-answer")
    first = p.complete_sync("describe", image=b"\x89PNGfake")
    second = p.complete_sync("describe", image=b"\x89PNGfake")
    assert first == "cached-answer"
    assert second == "cached-answer"
    assert p.calls == 1


def test_cache_key_changes_with_image_bytes(monkeypatch, tmp_path):
    monkeypatch.setenv("PDFVAULT_CACHE_DIR", str(tmp_path))
    k1 = cache_key(prompt="p", model="m", image=b"AAA")
    k2 = cache_key(prompt="p", model="m", image=b"BBB")
    k3 = cache_key(prompt="p", model="m", image=None)
    assert k1 != k2
    assert k1 != k3
    assert k2 != k3


def test_cache_atomic_write(monkeypatch, tmp_path):
    monkeypatch.setenv("PDFVAULT_CACHE", "1")
    monkeypatch.setenv("PDFVAULT_CACHE_DIR", str(tmp_path))
    key = cache_key(prompt="x", model="fake-model", image=None, provider="fake")
    shard = tmp_path / key[:2]
    shard.mkdir(parents=True, exist_ok=True)
    final_path = shard / f"{key[2:]}.txt"
    tmp_for_write = final_path.with_suffix(final_path.suffix + ".tmp")
    tmp_for_write.write_text("partial-write")
    # No rename happened — final_path should not exist yet.
    assert not final_path.exists()
    p = _FakeProvider(response="real")
    out = p.complete_sync("x")
    assert out == "real"
    assert final_path.exists()
    assert final_path.read_text() == "real"


def test_corrupt_cache_file_treated_as_miss(monkeypatch, tmp_path):
    monkeypatch.setenv("PDFVAULT_CACHE", "1")
    monkeypatch.setenv("PDFVAULT_CACHE_DIR", str(tmp_path))
    key = cache_key(prompt="q", model="fake-model", image=None, provider="fake")
    shard = tmp_path / key[:2]
    shard.mkdir(parents=True, exist_ok=True)
    final_path = shard / f"{key[2:]}.txt"
    # Write invalid UTF-8 bytes — read_text(utf-8) will raise.
    final_path.write_bytes(b"\xff\xfe\x00garbage\x80")
    p = _FakeProvider(response="recovered")
    out = p.complete_sync("q")
    assert out == "recovered"
    assert p.calls == 1
