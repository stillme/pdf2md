"""Tests for the batch driver."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from pdf2md.batch import (
    BatchProgress,
    BatchSummary,
    PaperResult,
    discover_pdfs,
    run_batch,
)
from pdf2md.document import Document, Metadata


def _fake_doc(text: str = "# Hello") -> Document:
    return Document(markdown=text, metadata=Metadata(pages=1))


class _FakeConvert:
    """Mock for pdf2md.convert that records calls and optionally raises / sleeps."""

    def __init__(
        self,
        *,
        sleep_s: float = 0.0,
        fail_for: set[str] | None = None,
        raise_exc: type[Exception] | None = RuntimeError,
    ) -> None:
        self.sleep_s = sleep_s
        self.fail_for = fail_for or set()
        self.raise_exc = raise_exc
        self.calls: list[str] = []
        self.start_times: list[tuple[str, float]] = []
        self.lock = threading.Lock()

    def __call__(self, source, **kwargs) -> Document:
        with self.lock:
            self.calls.append(source)
            self.start_times.append((source, time.monotonic()))
        if self.sleep_s:
            time.sleep(self.sleep_s)
        if Path(source).name in self.fail_for:
            raise self.raise_exc(f"forced failure for {source}")  # type: ignore[misc]
        return _fake_doc(f"# {Path(source).stem}")


@pytest.fixture
def fake_pdfs(tmp_path: Path) -> list[Path]:
    """Create three placeholder PDF files (content irrelevant — convert is mocked)."""
    paths = []
    for name in ["a.pdf", "b.pdf", "c.pdf"]:
        p = tmp_path / "in" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"%PDF-1.4\n%fake")
        paths.append(p)
    return paths


def test_processes_all_files_in_order(fake_pdfs, tmp_path):
    out = tmp_path / "out"
    fake = _FakeConvert()

    summary = run_batch(
        fake_pdfs,
        output_dir=out,
        concurrency=1,
        convert_fn=fake,
    )

    assert summary.total == 3
    assert summary.completed == 3
    assert summary.failed == 0
    assert summary.skipped == 0
    assert [Path(c).name for c in fake.calls] == ["a.pdf", "b.pdf", "c.pdf"]
    for name in ["a", "b", "c"]:
        assert (out / f"{name}.md").exists()
        assert (out / f"{name}.json").exists()


def test_resume_skips_completed(fake_pdfs, tmp_path):
    out = tmp_path / "out"
    fake1 = _FakeConvert()
    run_batch(fake_pdfs, output_dir=out, convert_fn=fake1)
    assert len(fake1.calls) == 3

    # Second run on same output dir: no actual conversion should happen.
    fake2 = _FakeConvert()
    summary = run_batch(fake_pdfs, output_dir=out, convert_fn=fake2)

    assert fake2.calls == []
    assert summary.completed == 0
    assert summary.skipped == 3
    assert summary.failed == 0


def test_no_resume_reprocesses(fake_pdfs, tmp_path):
    out = tmp_path / "out"
    run_batch(fake_pdfs, output_dir=out, convert_fn=_FakeConvert())

    fake2 = _FakeConvert()
    summary = run_batch(
        fake_pdfs, output_dir=out, convert_fn=fake2, resume=False,
    )
    assert len(fake2.calls) == 3
    assert summary.completed == 3
    assert summary.skipped == 0


def test_per_paper_failure_doesnt_abort(fake_pdfs, tmp_path):
    out = tmp_path / "out"
    fake = _FakeConvert(fail_for={"b.pdf"})

    summary = run_batch(fake_pdfs, output_dir=out, convert_fn=fake, concurrency=1)

    assert summary.total == 3
    assert summary.completed == 2
    assert summary.failed == 1
    assert summary.skipped == 0

    # Failed paper recorded in checkpoint with the error message.
    cp = json.loads((out / ".pdf2md-batch.json").read_text())
    failed_entries = [e for e in cp.values() if e["status"] == "failed"]
    assert len(failed_entries) == 1
    assert "forced failure" in failed_entries[0]["error"]

    # Other papers still produced outputs.
    assert (out / "a.md").exists()
    assert (out / "c.md").exists()
    assert not (out / "b.md").exists()


def test_failed_paper_retried_on_next_run(fake_pdfs, tmp_path):
    """Resume only skips ``completed`` entries — failures should be retried."""
    out = tmp_path / "out"
    fake1 = _FakeConvert(fail_for={"b.pdf"})
    run_batch(fake_pdfs, output_dir=out, convert_fn=fake1)

    # On retry with a non-failing converter, b.pdf should be reprocessed.
    fake2 = _FakeConvert()
    summary = run_batch(fake_pdfs, output_dir=out, convert_fn=fake2)

    # a and c were completed -> skipped. b was failed -> retried successfully.
    assert summary.skipped == 2
    assert summary.completed == 1
    assert [Path(c).name for c in fake2.calls] == ["b.pdf"]


def test_concurrency_parallelizes(fake_pdfs, tmp_path):
    out = tmp_path / "out"
    fake = _FakeConvert(sleep_s=0.2)

    t0 = time.monotonic()
    summary = run_batch(
        fake_pdfs, output_dir=out, convert_fn=fake, concurrency=3,
    )
    elapsed = time.monotonic() - t0

    assert summary.completed == 3
    # Sequential would take ~0.6s. With 3 workers, well under 0.5s.
    assert elapsed < 0.5, f"expected parallel speedup, took {elapsed:.2f}s"

    # All three start times should be within a small window of each other,
    # confirming they ran simultaneously rather than back-to-back.
    starts = sorted(t for _, t in fake.start_times)
    assert starts[-1] - starts[0] < 0.1


def test_progress_callback_invoked(fake_pdfs, tmp_path):
    out = tmp_path / "out"
    events: list[BatchProgress] = []

    run_batch(
        fake_pdfs,
        output_dir=out,
        convert_fn=_FakeConvert(),
        on_progress=events.append,
    )

    statuses = [e.status for e in events]
    assert statuses.count("started") == 3
    assert statuses.count("completed") == 3


def test_summary_is_pydantic_model(fake_pdfs, tmp_path):
    out = tmp_path / "out"
    summary = run_batch(fake_pdfs, output_dir=out, convert_fn=_FakeConvert())
    assert isinstance(summary, BatchSummary)
    assert all(isinstance(r, PaperResult) for r in summary.results)
    # Round-trips through JSON for downstream consumers.
    payload = summary.model_dump_json()
    assert "completed" in payload


def test_checkpoint_atomic_write(fake_pdfs, tmp_path):
    """Checkpoint should not leave a partial .tmp file behind on success."""
    out = tmp_path / "out"
    run_batch(fake_pdfs, output_dir=out, convert_fn=_FakeConvert())

    cp = out / ".pdf2md-batch.json"
    assert cp.exists()
    assert not (out / ".pdf2md-batch.json.tmp").exists()
    state = json.loads(cp.read_text())
    assert len(state) == 3
    assert all(v["status"] == "completed" for v in state.values())


def test_custom_checkpoint_path(fake_pdfs, tmp_path):
    out = tmp_path / "out"
    custom = tmp_path / "custom-checkpoint.json"

    run_batch(
        fake_pdfs,
        output_dir=out,
        checkpoint_path=custom,
        convert_fn=_FakeConvert(),
    )
    assert custom.exists()
    assert not (out / ".pdf2md-batch.json").exists()


def test_discover_pdfs_directory(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.pdf").write_bytes(b"x")
    (tmp_path / "ignore.txt").write_text("nope")

    found = discover_pdfs(tmp_path)
    names = [p.name for p in found]
    assert "a.pdf" in names
    assert "b.pdf" in names
    assert "ignore.txt" not in names


def test_discover_pdfs_single_file(tmp_path):
    p = tmp_path / "one.pdf"
    p.write_bytes(b"x")
    found = discover_pdfs(p)
    assert found == [p]


def test_discover_pdfs_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        discover_pdfs(tmp_path / "nope.pdf")
