"""Run the production PDF worker inside the final executable, without UI or AI."""

import hashlib
import json
import multiprocessing
import multiprocessing.spawn
import sys
from pathlib import Path
from unittest.mock import patch

from tutor_ai import __version__
from tutor_ai.pdf_worker import inspect


def main():
    root = Path(__file__).resolve().parent.parent
    exe = root / "dist" / f"Tutor-AI-{__version__}.exe"
    raw = (Path.home() / "Downloads/Учебники/Algebra_7_klass.pdf").read_bytes()
    original = multiprocessing.spawn.get_preparation_data

    def preparation(name):
        data = original(name)
        # The external test driver is deliberately absent from the product bundle.
        data.pop("init_main_from_name", None)
        data.pop("init_main_from_path", None)
        return data

    multiprocessing.set_executable(str(exe))
    try:
        with patch.object(sys, "frozen", True, create=True), patch.object(multiprocessing.spawn, "get_preparation_data", preparation):
            result = inspect(raw, pages=[254, 255, 256], render=True)
    finally:
        multiprocessing.set_executable(sys.executable)
    record = {"passed": result["pages"] == 257 and len(result["selected"]) == 3
              and all(p.get("image") for p in result["selected"]),
              "exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
              "source_sha256": hashlib.sha256(raw).hexdigest(),
              "pages": result["pages"], "rendered": [p["pdf_page"] for p in result["selected"]],
              "recognition": "no OCR: PDF decoding and raster only"}
    (root / "build/uf29-frozen-pdf.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record))
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
