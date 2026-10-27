"""Own visible synthetic window; compare screen pixels with widget and DOM.

No external window capture or input injection. Windows actions use computer-use.
"""
import json
import sys
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QTimer

ROOT = Path(__file__).resolve().parent.parent
BASELINE = "--baseline" in sys.argv
if BASELINE:
    sys.path.insert(0, str(ROOT / "build/source040-upgrade"))

from tutor_ai.desktop import run  # noqa: E402
from tutor_ai.service import Service  # noqa: E402


def main():
    version = "0.4.0" if BASELINE else "0.4.1"
    folder = ROOT / "build" / ("visible-feedback-" + version + "-" + uuid.uuid4().hex[:8])
    folder.mkdir()
    events = []
    def factory(data):
        service = Service(data)
        service.register("Synthetic parent", "synthetic-parent-password", "PARENT")
        service.register("Synthetic child", "synthetic-child-password", "STUDENT", {
            "region": "Region", "city": "City", "school": "School", "grade": 7, "address": {"mode": "manual"}})
        return service
    def hook(window, page, service):
        window.setWindowTitle("Tutor-AI · Pixel probe " + version)
        previous = [None]
        timer = QTimer(window)
        def record(value):
            if not isinstance(value, dict) or value.get("route") == previous[0]:
                return
            previous[0] = value["route"]
            def capture():
                index = len(events)
                # grabWindow reads on-screen pixels; the separate widget grab
                # requests a rendering of the application surface.
                active = window.isActiveWindow()
                screen = window.screen().grabWindow(window.winId()) if active else None
                if screen is not None:
                    screen.save(str(folder / f"{index}-screen.png"))
                window.grab().save(str(folder / f"{index}-widget.png"))
                events.append({**value, "at_monotonic": time.monotonic(), "active": active,
                               "screen_null": screen.isNull() if screen is not None else None,
                               "screen_skipped": not active, "index": index})
                (folder / "events.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
            QTimer.singleShot(300, capture)
        timer.timeout.connect(lambda: page.runJavaScript(
            "typeof state!=='undefined'&&state.data?({route:state.route,heading:document.querySelector('.content h1')?.textContent}):null", record))
        timer.start(200)
        QTimer.singleShot(240000, window.close)
        print(json.dumps({"directory": str(folder), "version": version}), flush=True)
    return run(root_override=folder, service_factory=factory, test_hook=hook)


if __name__ == "__main__":
    raise SystemExit(main())
