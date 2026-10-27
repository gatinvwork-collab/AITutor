"""Fresh independent regression; synthetic data only."""
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
meta={"platform":platform.platform(),"python":sys.version,
      "packages":{n:importlib.metadata.version(n) for n in ("pytest","PySide6","cryptography","httpx")}}
files=[*ROOT.glob("aitutor/*.py"),*ROOT.glob("ui/*"),*ROOT.glob("tests/*"),
       ROOT/"main.py",ROOT/"dist/AI-Tutor-0.3.2.exe"]
meta["sha256"]={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in files if p.is_file()}
git=["git","-c","safe.directory="+ROOT.as_posix()]
for key,args in (("commit",["rev-parse","HEAD"]),("git_status",["status","--short"])):
    r=subprocess.run(git+args,cwd=ROOT,capture_output=True,text=True,encoding="utf-8",errors="replace")
    meta[key]=r.stdout.strip()
(OUT/"environment.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding="utf-8")
runs=[]
def run(name,args):
    with (OUT/(name+".log")).open("w",encoding="utf-8") as log:
        r=subprocess.run(args,cwd=ROOT,env={**os.environ,"PYTHONUTF8":"1"},stdout=log,stderr=subprocess.STDOUT)
    record={"name":name,"returncode":r.returncode,"command":args}
    runs.append(record)
    (OUT/"runs.json").write_text(json.dumps(runs,indent=2),encoding="utf-8")
    print(json.dumps(record),flush=True)
run("native",[sys.executable,"-X","utf8","-m","pytest","tests",
    "docs/evidence/qa-review-2026-10-26/test_exploratory.py",
    "docs/evidence/qa-retest-0.3.1-2026-10-26/test_extended.py",
    "docs/evidence/qa-retest-0.3.1-2026-10-26/test_supplementary.py",
    "-k","not test_long_text_import_is_complete_or_warns_about_truncation","-q",
    "--basetemp=build/qa-retest032-native","--junitxml="+str(OUT/"native.xml")])
run("original-independent-gui",[sys.executable,"-X","utf8",
    "docs/evidence/qa-review-2026-10-26/gui_exploratory.py"])
for module in ("tests.gui_smoke","tests.gui_feedback_03","tests.gui_qa_031","tests.gui_qa_032","tests.gui_import_032"):
    run(module.replace(".","-"),[sys.executable,"-X","utf8","-m",module])
run("ruff",[sys.executable,"-m","ruff","check","aitutor","tests","main.py"])
(OUT/"regression-complete.json").write_text(json.dumps({"complete":True,"runs":len(runs)}),encoding="utf-8")
