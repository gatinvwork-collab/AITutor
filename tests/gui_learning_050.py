"""Real Qt UI workflows using an explicitly synthetic network provider."""

import uuid
from pathlib import Path

from tests import gui_feedback_03 as harness
from tests.test_learning_050 import BankProvider
from tutor_ai.service import Service


class DemoProvider(BankProvider):
    def send_message(self, messages):
        if messages[0]["content"].startswith(("Сгенерируй", "Проверь решения")):
            return super().send_message(messages)
        return {
            "text": "**Проверка решения**\nПереходы следует обосновать. $\\frac{1}{2}$",
            "usage": {"input_tokens": 10, "output_tokens": 10},
        }


def main():
    harness.ROOT = (
        Path(__file__).resolve().parent.parent / "build" / ("gui-learning050-" + uuid.uuid4().hex[:8])
    )
    harness.SCRIPT = Path(__file__).with_suffix(".js").read_text(encoding="utf-8")
    # Reuse capture and timeout plumbing, preserving its real WebView execution.
    harness.Service = lambda root, **kwargs: Service(root, provider_factory=DemoProvider)
    return harness.main()


if __name__ == "__main__":
    raise SystemExit(main())
