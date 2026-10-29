"""Isolated interactive window for physical mouse/keyboard QA. No user data."""

from pathlib import Path
import json
import time

from PySide6.QtCore import QTimer
from tutor_ai.desktop import run
from tutor_ai.service import Service
from tests.test_application import FakeProvider

ROOT = Path(__file__).resolve().parent.parent / "build/uf29-physical-source"


class TestService(Service):
    def __init__(self, root):
        super().__init__(root, provider_factory=FakeProvider)

    def learning(self, action, **args):
        if action == "overview":
            time.sleep(2)  # Deliberately slow read to inspect unrelated controls.
        return super().learning(action, **args)


def main():
    if not (ROOT / "app-data/data/vault.aead").exists():
        seed = TestService(ROOT / "app-data")
        seed.register("UF29 Parent", "uf29-parent-password", "PARENT")
        seed.register("UF29 Child", "uf29-child-password", "STUDENT", {
            "region": "Region", "city": "City", "school": "School", "grade": 7})
        seed.logout()

    def hook(window, page, service):
        window.setWindowTitle("UF29 — isolated source physical QA")
        timer = QTimer(window)
        window.uf29_timer = timer
        def observe():
            def record(value):
                if value:
                    (ROOT / "observation.json").write_text(json.dumps(value), encoding="utf-8")
            page.runJavaScript("({route:typeof state!=='undefined'?state.route:null,inFlight:typeof inFlight!=='undefined'?inFlight:null,focused:document.activeElement?.name||document.activeElement?.id||'',auth:!!document.querySelector('form[data-form=login]'),busy:!document.querySelector('#busy').hidden,scrollY:scrollY,width:innerWidth,height:innerHeight,dpr:devicePixelRatio})", record)
        timer.timeout.connect(observe)
        timer.start(500)
        page.loadFinished.connect(lambda _: window.grab().save(str(ROOT / "initial.png")))
    return run(root_override=ROOT, service_factory=TestService, test_hook=hook)


if __name__ == "__main__":
    raise SystemExit(main())
