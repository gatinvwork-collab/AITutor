"""Real native directory picker/transfer/login; all data synthetic and isolated."""
import json
import uuid
from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from tutor_ai.crypto import seal
from tutor_ai.service import Service
from tutor_ai.transfer import inventory
from tests import gui_feedback_03 as harness
from tests.test_application import PASSWORD, CHILD_PASSWORD, PROFILE


def main():
    output = Path(__file__).resolve().parent.parent / "build" / ("gui-transfer040-" + uuid.uuid4().hex[:8])
    source = output / "source"
    old = Service(source / "app-data")
    parent = old.register("Родитель AI-Tutor", PASSWORD, "PARENT")
    child = old.register("Старый ученик", CHILD_PASSWORD, "STUDENT", PROFILE)
    with old.store.transaction():
        old.store.put("homework", "old-work", {"id": "old-work", "student": child["id"],
            "text": "AI-Tutor history remains", "filename": "old.txt",
            "original": seal(old.store.attachment_key(), b"old original", b"old-work")}, child["id"])
    old.store.close()
    before = inventory(source / "app-data")
    picker = QFileDialog.getExistingDirectory
    QFileDialog.getExistingDirectory = staticmethod(lambda *_args, **_kwargs: str(source))
    harness.ROOT = output / "run"
    login = {"id": parent["id"], "password": PASSWORD}
    harness.SCRIPT = "window.__transferLogin=" + json.dumps(login) + ";\n" + Path(__file__).with_suffix(".js").read_text(encoding="utf-8")
    try:
        result = harness.main()
        assert inventory(source / "app-data") == before
        return result
    finally:
        QFileDialog.getExistingDirectory = picker


if __name__ == "__main__":
    raise SystemExit(main())
