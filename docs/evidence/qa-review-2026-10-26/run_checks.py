"""Capture reproducible logs as UTF-8; no user app-data accessed."""
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
def execute(name, args):
    run = subprocess.run(args, cwd=ROOT, text=True, encoding="utf-8", errors="replace",
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (OUT / (name + ".log")).write_text(run.stdout, encoding="utf-8")
    return {"name": name, "returncode": run.returncode, "command": args}

meta = {"platform": platform.platform(), "python": sys.version,
        "packages": {name: importlib.metadata.version(name) for name in
                     ("pytest", "PySide6", "cryptography", "httpx")}}
git = ["git", "-c", "safe.directory=" + ROOT.as_posix()]
meta["commit"] = subprocess.run(git + ["rev-parse", "HEAD"], cwd=ROOT,
    capture_output=True, text=True).stdout.strip()
meta["git_status"] = subprocess.run(git + ["status", "--short"], cwd=ROOT,
    capture_output=True, text=True).stdout
meta["sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted([*ROOT.glob("aitutor/*.py"), *ROOT.glob("ui/*"), ROOT/"main.py",
                     ROOT/"dist/AI-Tutor-0.3.exe"]) if p.is_file()}
meta["runs"] = [
    execute("baseline", [sys.executable, "-X", "utf8", "-m", "pytest", "-q",
        "--basetemp=build/qa-review-native-final", "--junitxml=" + str(OUT/"baseline.xml")]),
    execute("exploratory", [sys.executable, "-X", "utf8", "-m", "pytest",
        str(OUT/"test_exploratory.py"), "-q", "--basetemp=build/qa-review-extra-final",
        "--junitxml=" + str(OUT/"exploratory.xml")]),
    execute("ruff", [sys.executable, "-m", "ruff", "check", "aitutor", "tests", "main.py"]),
    execute("gui_exploratory", [sys.executable, "-X", "utf8", str(OUT/"gui_exploratory.py")])
]
(OUT/"environment-and-runs.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(meta["runs"], indent=2))
