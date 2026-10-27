"""Real WebView focus and navigation under an outstanding command, no provider."""
import uuid
from pathlib import Path

from tests import gui_feedback_03 as harness


def main():
    harness.ROOT = Path(__file__).resolve().parent.parent / "build" / ("gui-feedback041-" + uuid.uuid4().hex[:8])
    harness.SCRIPT = Path(__file__).with_suffix(".js").read_text(encoding="utf-8")
    original_run = harness.run
    def run(**kwargs):
        return original_run(**kwargs, diagnostics=True)
    harness.run = run
    try:
        return harness.main()
    finally:
        harness.run = original_run


if __name__ == "__main__":
    raise SystemExit(main())
