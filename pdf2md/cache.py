"""Content-addressed cache for VLM provider responses."""
from __future__ import annotations
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Callable

_LOG = logging.getLogger(__name__)


def cache_dir() -> Path:
    override = os.environ.get("PDF2MD_CACHE_DIR")
    base = Path(override) if override else Path.home() / ".cache" / "pdf2md"
    base.mkdir(parents=True, exist_ok=True)
    return base


def cache_enabled() -> bool:
    return os.environ.get("PDF2MD_CACHE", "") == "1"


def cache_key(*, prompt: str, model: str, image: bytes | None = None, **extra) -> str:
    image_hash = hashlib.sha256(image).hexdigest() if image else ""
    payload = {
        "prompt": prompt,
        "model": model,
        "image_sha256": image_hash,
        "extra": {k: extra[k] for k in sorted(extra)},
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _path_for(key: str) -> Path:
    return cache_dir() / key[:2] / f"{key[2:]}.txt"


def cache_get(key: str) -> str | None:
    path = _path_for(key)
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        _LOG.debug("cache read failed for %s: %s", key, exc)
        return None


def cache_set(key: str, value: str) -> None:
    path = _path_for(key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(value, encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:
        _LOG.debug("cache write failed for %s: %s", key, exc)


def cached_call(
    fn: Callable[[], str],
    *,
    prompt: str,
    model: str,
    image: bytes | None = None,
    **extra,
) -> str:
    """Run fn() with caching when PDF2MD_CACHE=1; otherwise just call fn()."""
    if not cache_enabled():
        return fn()
    key = cache_key(prompt=prompt, model=model, image=image, **extra)
    hit = cache_get(key)
    if hit is not None:
        return hit
    value = fn()
    cache_set(key, value)
    return value
