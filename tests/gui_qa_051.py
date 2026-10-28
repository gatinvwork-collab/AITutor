import uuid
from pathlib import Path
from tests import gui_feedback_03 as harness


def main():
    harness.ROOT = Path(__file__).resolve().parent.parent / "build" / ("gui-qa051-" + uuid.uuid4().hex[:8])
    harness.SCRIPT = Path(__file__).with_suffix(".js").read_text(encoding="utf-8")
    return harness.main()


if __name__ == "__main__":
    raise SystemExit(main())
