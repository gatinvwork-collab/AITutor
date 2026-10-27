"""Independent retest; only synthetic data and local mocks."""
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
env = {**os.environ, "PYTHONUTF8": "1"}
meta = {"platform": platform.platform(), "python": sys.version,
        "packages": {n: importlib.metadata.version(n) for n in ("pytest","PySide6","cryptography","httpx")}}
paths = [*ROOT.glob("aitutor/*.py"), *ROOT.glob("ui/*"), *ROOT.glob("tests/*"),
         ROOT/"main.py", ROOT/"dist/AI-Tutor-0.3.1.exe"]
meta["sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in paths if p.is_file()}
git = ["git","-c","safe.directory="+ROOT.as_posix()]
for name, args in [("commit",["rev-parse","HEAD"]),("git_status",["status","--short"])]:
    r = subprocess.run(git+args,cwd=ROOT,capture_output=True,text=True,encoding="utf-8",errors="replace")
    meta[name] = r.stdout.strip()
(OUT/"environment.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding="utf-8")
runs = []
def run(name,args,timeout=240):
    try:
        r = subprocess.run(args,cwd=ROOT,env=env,text=True,encoding="utf-8",errors="replace",
                           capture_output=True,timeout=timeout)
        output = r.stdout+r.stderr
        record = {"name":name,"returncode":r.returncode,"command":args}
    except subprocess.TimeoutExpired:
        output = "QA harness timeout"
        record = {"name":name,"status":"blocked","reason":output}
    (OUT/(name+".log")).write_text(output,encoding="utf-8")
    runs.append(record)
    (OUT/"runs.json").write_text(json.dumps(runs,indent=2),encoding="utf-8")
    print(json.dumps(record),flush=True)

run("native",[sys.executable,"-X","utf8","-m","pytest","-q",
    "--basetemp=build/qa-retest031-native","--junitxml="+str(OUT/"native.xml")])
run("original-independent-native",[sys.executable,"-X","utf8","-m","pytest",
    "docs/evidence/qa-review-2026-10-26/test_exploratory.py","-q",
    "--basetemp=build/qa-retest031-original","--junitxml="+str(OUT/"original-independent-native.xml")])
run("original-independent-gui",[sys.executable,"-X","utf8",
    "docs/evidence/qa-review-2026-10-26/gui_exploratory.py"])
for module in ("tests.gui_smoke","tests.gui_feedback_03","tests.gui_qa_031"):
    run(module.replace(".","-"),[sys.executable,"-X","utf8","-m",module])
run("ruff",[sys.executable,"-m","ruff","check","aitutor","tests","main.py"])
