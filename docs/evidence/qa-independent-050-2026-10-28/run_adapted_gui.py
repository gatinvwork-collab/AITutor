"""Adapt prior scenarios to current forms/version without editing the existing suite."""
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from tests import gui_feedback_03 as harness
from tests import gui_transfer_040 as transfer
from PySide6.QtWidgets import QFileDialog

if "--transfer" in sys.argv:
    original = harness.main

    def adapted():
        harness.SCRIPT = harness.SCRIPT.replace("state.status.version==='0.4.0'", "state.status.version==='0.5.0a1'")
        return original()

    harness.main = adapted
    raise SystemExit(transfer.main())

folder = ROOT / "build" / ("qa-current-homework050-" + uuid.uuid4().hex[:8])
folder.mkdir()
small, large = folder / "short.txt", folder / "long.txt"
small.write_text("QA short original", encoding="utf-8")
large.write_text("x" * 30001, encoding="utf-8")
choices = iter([(str(small), ""), (str(large), ""), ("", "")])
original = QFileDialog.getOpenFileName
QFileDialog.getOpenFileName = staticmethod(lambda *_a, **_kw: next(choices))
harness.ROOT = folder / "run"
harness.SCRIPT = (OUT / "gui_current_homework.js").read_text(encoding="utf-8")
try:
    raise SystemExit(harness.main())
finally:
    QFileDialog.getOpenFileName = original
