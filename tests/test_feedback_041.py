"""Bounded accounting queue and opt-in, content-free diagnostics."""
import json
import threading

import pytest

from tutor_ai.diagnostics import Diagnostics
from tutor_ai.errors import AppError
from tutor_ai.worker import NativeWorker


def test_long_command_does_not_accumulate_periodic_ticks():
    entered, release = threading.Event(), threading.Event()
    observed, ticks = [], []
    worker = NativeWorker(observe=lambda **timing: observed.append(timing))
    def blocked():
        entered.set()
        assert release.wait(5)
    future = worker.submit(blocked, label="test_provider")
    assert entered.wait(5)
    try:
        for _ in range(1000):
            assert worker.submit_idle(lambda: ticks.append(True)) is None
        assert worker.pending == 1 and not ticks
    finally:
        release.set()
        future.result(timeout=5)
    tick = worker.submit_idle(lambda: ticks.append(True))
    tick.result(timeout=5)
    worker.shutdown(wait=True)
    assert ticks == [True] and worker.pending == 0
    assert [row["command"] for row in observed] == ["test_provider", "tick"]


def test_foreground_queue_bounded_and_recovers_after_error():
    release = threading.Event()
    worker = NativeWorker(limit=2)
    first = worker.submit(lambda: release.wait(5))
    second = worker.submit(lambda: (_ for _ in ()).throw(ValueError("synthetic")))
    try:
        with pytest.raises(AppError) as error:
            worker.submit(lambda: None)
        assert error.value.code == "busy" and worker.pending == 2
    finally:
        release.set()
    first.result(timeout=5)
    with pytest.raises(ValueError):
        second.result(timeout=5)
    assert worker.submit(lambda: 42).result(timeout=5) == 42
    worker.shutdown(wait=True)
    assert worker.pending == 0 and worker.submit_idle(lambda: None) is None


def test_cancelled_queued_task_releases_slot():
    release = threading.Event()
    worker = NativeWorker()
    first = worker.submit(lambda: release.wait(5))
    queued = worker.submit(lambda: None)
    assert queued.cancel()
    assert worker.pending == 1
    release.set()
    first.result(timeout=5)
    worker.shutdown(wait=True)
    assert worker.pending == 0


def test_diagnostics_opt_in_only_and_whitelist(tmp_path):
    disabled = Diagnostics(tmp_path)
    disabled.command("snapshot", 2, 3)
    assert not list(tmp_path.iterdir())
    log = Diagnostics(tmp_path, enabled=True, commands={"snapshot"})
    log.command("snapshot", 12, 34)
    log.command("PASSWORD-AND-API-KEY", 0, 1)
    log.navigation({"route": "students", "render_ms": 5, "raf_ms": 30, "width": 1280,
                    "height": 880, "dpr": 2, "text": "PRIVATE-LESSON", "account": "PRIVATE-ID"})
    log.navigation({"route": "PRIVATE-PROFILE", "render_ms": 5})
    log.command("snapshot", float("nan"), -5)
    rows = [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]
    assert rows[1] == {"event": "command", "command": "snapshot", "wait_ms": 12, "duration_ms": 34}
    assert rows[2]["command"] == "unknown" and rows[-1]["wait_ms"] is None
    assert rows[-1]["duration_ms"] is None
    raw = log.path.read_text(encoding="utf-8")
    assert all(secret not in raw for secret in ("PASSWORD", "API-KEY", "PRIVATE"))


def test_diagnostics_cannot_fill_disk_or_fail_product_operation(tmp_path, monkeypatch):
    log = Diagnostics(tmp_path, enabled=True)
    log.path.write_bytes(b"x" * (2 * 1024 * 1024))
    log.command("tick", 1, 2)
    assert log.path.stat().st_size == 2 * 1024 * 1024
    def fail(*_, **__):
        raise OSError("no space")
    monkeypatch.setattr(type(log.path), "open", fail)
    log.command("tick", 3, 4)
