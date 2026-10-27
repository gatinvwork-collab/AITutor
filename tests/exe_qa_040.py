"""Previous timer/import/privacy suites against the renamed frozen executable."""
from pathlib import Path

from tests.exe_qa_032 import main as regression


if __name__ == "__main__":
    raise SystemExit(regression(Path(__file__).resolve().parent.parent / "dist" / "Tutor-AI-0.4.0.exe"))
