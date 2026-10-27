"""Actual bridge/import with a test-controlled native file picker."""
import uuid
from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from tutor_ai.service import Service
from tests import gui_feedback_03 as harness
from tests.qa_fixtures import seed_import_032
from tests.test_application import FakeProvider


def main():
    harness.ROOT = Path(__file__).resolve().parent.parent / "build" / ("gui-import032-" + uuid.uuid4().hex[:8])
    harness.ROOT.mkdir(parents=True)
    small, long = harness.ROOT / "small.txt", harness.ROOT / "long.txt"
    small.write_text("Short question", encoding="utf-8")
    long.write_text("x" * 30000 + "\nFINAL QUESTION", encoding="utf-8")
    choices = iter([(str(small), ""), (str(long), ""), ("", "")])
    picker = QFileDialog.getOpenFileName
    QFileDialog.getOpenFileName = staticmethod(lambda *_args, **_kwargs: next(choices))
    class FixtureService(Service):
        def register(self, *args, **kwargs):
            result = super().register(*args, **kwargs)
            if self.store.user(result["id"])["role"] == "STUDENT":
                seed_import_032(self, result["id"])
            return result

    original_run = harness.run
    def run(**kwargs):
        kwargs["service_factory"] = lambda root: FixtureService(root, provider_factory=FakeProvider)
        return original_run(**kwargs)
    harness.run = run
    harness.SCRIPT = "window.__qaUsePicker=true;\n" + Path(__file__).with_suffix(".js").read_text(encoding="utf-8")
    # main creates its output directory itself; fixtures live beside it.
    fixture_root = harness.ROOT
    harness.ROOT = fixture_root / "run"
    try:
        return harness.main()
    finally:
        QFileDialog.getOpenFileName = picker
        harness.run = original_run


if __name__ == "__main__":
    raise SystemExit(main())
