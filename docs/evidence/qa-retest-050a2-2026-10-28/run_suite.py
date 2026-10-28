"""Read-only product QA; new synthetic folders, isolated logs, no live models."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
os.environ["PATH"] = r"C:\Users\591053\AppData\Local\JetBrains\PyCharm2026.2\acp-agents\.runtimes\node\24.19.0" + os.pathsep + os.environ["PATH"]
sys.path.insert(0, str(ROOT))
mode = sys.argv[1]
if mode == "gui":
    modules = ["gui_smoke", "gui_feedback_03", "gui_qa_031", "gui_qa_032", "gui_import_032",
               "gui_feedback_041", "gui_transfer_040", "gui_learning_050", "gui_qa_051"]
elif mode == "exe":
    modules = ["exe_learning_050", "exe_qa_051"]
else:
    raise ValueError(mode)
results = []
for name in modules:
    started = time.monotonic()
    with (OUT / (name + ".log")).open("wb") as log:
        try:
            child = subprocess.run([sys.executable, "-X", "utf8", "-m", "tests." + name], cwd=ROOT,
                                   stdout=log, stderr=log, timeout=230, env=os.environ.copy())
            code = child.returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
    item = {"module": name, "exit_code": code, "seconds": round(time.monotonic()-started, 2)}
    results.append(item)
    (OUT / (mode + "-summary.json")).write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(item), flush=True)

if mode == "exe":
    source = ROOT / "build/qa051-a1-source-final"
    assert shutil.disk_usage(ROOT).free > 40 * 1024**2, "Insufficient space for isolated upgrade fixture"
    before = hashlib.sha256((source / "app-data/data/vault.aead").read_bytes()).hexdigest()
    target = ROOT / "build" / ("qa-retest-a2-upgrade-" + uuid.uuid4().hex[:8])
    target.mkdir()
    shutil.copytree(source / "app-data", target / "app-data")
    shutil.copy2(source / "expected.json", target / "expected.json")
    with (OUT / "upgrade-a1-native.log").open("wb") as log:
        child = subprocess.run([sys.executable, "-X", "utf8", "-m", "tests.upgrade_051", "verify", str(target)],
                               cwd=ROOT, stdout=log, stderr=log, timeout=100)
    data = {"exit_code": child.returncode, "target": str(target), "source_unchanged": before ==
            hashlib.sha256((source / "app-data/data/vault.aead").read_bytes()).hexdigest()}
    (OUT / "upgrade-a1-native-summary.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps(data), flush=True)
    if child.returncode or not data["source_unchanged"]:
        results.append({"exit_code": 1})
raise SystemExit(0 if all(r["exit_code"] == 0 for r in results) else 1)
