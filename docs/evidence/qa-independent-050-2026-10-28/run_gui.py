"""Run existing real Qt/WebView regression scripts on synthetic data only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
modules = ["gui_smoke", "gui_feedback_03", "gui_qa_031", "gui_qa_032",
           "gui_import_032", "gui_feedback_041", "gui_transfer_040"]
results = []
for name in modules:
    started = time.monotonic()
    with (OUT / (name + ".log")).open("wb") as log:
        try:
            p = subprocess.run([sys.executable, "-X", "utf8", "-m", "tests." + name],
                               cwd=ROOT, stdout=log, stderr=log, timeout=240, env=os.environ.copy())
            code = p.returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
    results.append({"module": name, "exit_code": code, "seconds": round(time.monotonic()-started, 2)})
    (OUT / "gui-summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results[-1]), flush=True)
raise SystemExit(0 if all(r["exit_code"] == 0 for r in results) else 1)
