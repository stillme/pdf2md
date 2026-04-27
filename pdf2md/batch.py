"""Batch driver — convert a corpus of PDFs with checkpointing and concurrency.

Designed for overnight "daily screener" runs over hundreds of biomedical
PDFs. Resumable after Ctrl-C / crash, per-paper failures isolated.

Concurrency: ``ThreadPoolExecutor``. ``pdf2md.convert`` releases the GIL
during pdfium / subprocess / network I/O. Default 1 because subscription
providers (claude-cli) hit rate limits hard at N>1.

Checkpoint: single JSON file mapping absolute paper path to
``{status, error, duration_s, completed_at}``. Atomic write-then-rename
after every paper so a SIGKILL mid-batch loses at most one in-flight paper.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class PaperResult(BaseModel):
    path: str
    status: str  # "completed" | "failed" | "skipped"
    error: str | None = None
    duration_s: float = 0.0
    output_md: str | None = None
    output_json: str | None = None


class BatchSummary(BaseModel):
    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    total_duration_s: float = 0.0
    results: list[PaperResult] = Field(default_factory=list)


@dataclass
class BatchProgress:
    index: int  # 1-based
    total: int
    path: Path
    status: str  # "started" | "completed" | "failed" | "skipped"
    error: str | None = None
    duration_s: float = 0.0


class _Checkpoint:
    """JSON-backed checkpoint with atomic writes and a single mutex."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._state: dict[str, dict] = {}
        self._lock = threading.Lock()
        if path.exists():
            try:
                self._state = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("checkpoint %s unreadable (%s); starting fresh", path, exc)

    def get(self, key: str) -> dict | None:
        with self._lock:
            return self._state.get(key)

    def is_completed(self, key: str) -> bool:
        with self._lock:
            entry = self._state.get(key)
            return bool(entry and entry.get("status") == "completed")

    def record(self, key: str, entry: dict) -> None:
        # POSIX rename is atomic on the same filesystem, so a crash mid-write
        # leaves the prior checkpoint intact rather than truncated.
        with self._lock:
            self._state[key] = entry
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(self._state, indent=2, sort_keys=True))
            os.replace(tmp, self.path)


def discover_pdfs(input_path: Path | str) -> list[Path]:
    """Resolve a directory, file, or glob pattern to a sorted list of PDFs."""
    p = Path(input_path)
    if p.is_dir():
        return sorted(p.rglob("*.pdf"))
    if p.is_file():
        return [p]
    s = str(input_path)
    if any(ch in s for ch in "*?["):
        if Path(s).is_absolute():
            anchor = Path(s).anchor
            return sorted(Path(anchor).glob(str(Path(s).relative_to(anchor))))
        return sorted(Path(".").glob(s))
    raise FileNotFoundError(f"input path not found: {input_path}")


def run_batch(
    inputs: list[Path],
    output_dir: Path,
    *,
    tier: str = "standard",
    provider: str | None = None,
    figures: str = "describe",
    equations: bool = True,
    verify: bool = True,
    concurrency: int = 1,
    checkpoint_path: Path | None = None,
    resume: bool = True,
    on_progress: Callable[[BatchProgress], None] | None = None,
    convert_fn: Callable | None = None,
) -> BatchSummary:
    """Process a list of PDF paths with checkpointing and concurrency.

    ``convert_fn`` is the per-paper converter; tests inject a mock here, real
    callers should leave it ``None`` to use ``pdf2md.core.convert``.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if checkpoint_path is None:
        checkpoint_path = output_dir / ".pdf2md-batch.json"
    checkpoint = _Checkpoint(checkpoint_path)

    if convert_fn is None:
        from pdf2md.core import convert as convert_fn  # type: ignore[assignment]

    total = len(inputs)
    summary = BatchSummary(total=total)
    summary_lock = threading.Lock()

    def _emit(p: BatchProgress) -> None:
        if on_progress is not None:
            try:
                on_progress(p)
            except Exception as exc:
                logger.warning("on_progress raised: %s", exc)

    def _record_failure(key: str, pdf_path: Path, idx: int, err: str, duration: float) -> PaperResult:
        checkpoint.record(key, {
            "status": "failed", "error": err,
            "duration_s": duration, "completed_at": time.time(),
        })
        _emit(BatchProgress(
            index=idx, total=total, path=pdf_path,
            status="failed", error=err, duration_s=duration,
        ))
        return PaperResult(path=key, status="failed", error=err, duration_s=duration)

    def _process(idx: int, pdf_path: Path) -> PaperResult:
        key = str(pdf_path.resolve())

        if resume and checkpoint.is_completed(key):
            entry = checkpoint.get(key) or {}
            duration = float(entry.get("duration_s", 0.0))
            _emit(BatchProgress(
                index=idx, total=total, path=pdf_path,
                status="skipped", duration_s=duration,
            ))
            return PaperResult(
                path=key, status="skipped", duration_s=duration,
                output_md=str(output_dir / f"{pdf_path.stem}.md"),
                output_json=str(output_dir / f"{pdf_path.stem}.json"),
            )

        _emit(BatchProgress(index=idx, total=total, path=pdf_path, status="started"))
        t0 = time.monotonic()

        try:
            doc = convert_fn(
                str(pdf_path), tier=tier, figures=figures,
                verify=verify, provider=provider, equations=equations,
            )
        except Exception as exc:
            return _record_failure(
                key, pdf_path, idx,
                f"{type(exc).__name__}: {exc}",
                time.monotonic() - t0,
            )

        duration = time.monotonic() - t0
        md_path = output_dir / f"{pdf_path.stem}.md"
        json_path = output_dir / f"{pdf_path.stem}.json"
        try:
            doc.save_markdown(str(md_path))
            doc.save_json(str(json_path))
        except Exception as exc:
            return _record_failure(
                key, pdf_path, idx,
                f"save failed: {type(exc).__name__}: {exc}",
                duration,
            )

        checkpoint.record(key, {
            "status": "completed", "error": None,
            "duration_s": duration, "completed_at": time.time(),
        })
        _emit(BatchProgress(
            index=idx, total=total, path=pdf_path,
            status="completed", duration_s=duration,
        ))
        return PaperResult(
            path=key, status="completed", duration_s=duration,
            output_md=str(md_path), output_json=str(json_path),
        )

    t_start = time.monotonic()
    if concurrency <= 1:
        for i, pdf_path in enumerate(inputs, start=1):
            with summary_lock:
                summary.results.append(_process(i, pdf_path))
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futures = [ex.submit(_process, i, p) for i, p in enumerate(inputs, start=1)]
            for fut in as_completed(futures):
                with summary_lock:
                    summary.results.append(fut.result())

    summary.total_duration_s = time.monotonic() - t_start
    summary.completed = sum(1 for r in summary.results if r.status == "completed")
    summary.failed = sum(1 for r in summary.results if r.status == "failed")
    summary.skipped = sum(1 for r in summary.results if r.status == "skipped")
    summary.results.sort(key=lambda r: r.path)
    return summary


def format_summary_table(summary: BatchSummary) -> str:
    lines = [
        "", "=" * 60, "Batch Summary", "=" * 60,
        f"Total:     {summary.total}",
        f"Completed: {summary.completed}",
        f"Failed:    {summary.failed}",
        f"Skipped:   {summary.skipped}",
        f"Duration:  {summary.total_duration_s:.1f}s",
    ]
    if summary.failed:
        lines.append("")
        lines.append("Failures:")
        for r in summary.results:
            if r.status == "failed":
                lines.append(f"  - {r.path}: {r.error}")
    return "\n".join(lines)


def stderr_progress_printer() -> Callable[[BatchProgress], None]:
    """One line per state transition to stderr — no tqdm dependency."""
    def _print(p: BatchProgress) -> None:
        if p.status == "started":
            msg = f"[{p.index}/{p.total}] {p.path.name} ..."
        elif p.status == "completed":
            msg = f"[{p.index}/{p.total}] {p.path.name} OK ({p.duration_s:.1f}s)"
        elif p.status == "skipped":
            msg = f"[{p.index}/{p.total}] {p.path.name} skip (cached)"
        elif p.status == "failed":
            msg = f"[{p.index}/{p.total}] {p.path.name} FAIL: {p.error}"
        else:
            return
        print(msg, file=sys.stderr, flush=True)
    return _print
