import hashlib
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
screens=OUT/"screenshots"
screens.mkdir(exist_ok=True)
runs={}
for name in ("original-independent-gui","tests-gui_smoke","tests-gui_feedback_03","tests-gui_qa_031","exe"):
    lines=(OUT/(name+".log")).read_text(encoding="utf-8").strip().splitlines()
    data=next((json.loads(s) for s in reversed(lines) if s.startswith("{")),None)
    runs[name]=data
    if data and data.get("directory"):
        directory=Path(data["directory"])
        if (directory/"result.json").exists():
            shutil.copyfile(directory/"result.json",OUT/(name+"-result.json"))
        if name=="tests-gui_feedback_03":
            for p in directory.glob("*.png"):
                shutil.copyfile(p,screens/p.name)
        if name=="exe":
            for sub in ("workflow","historical","foreign-restore"):
                p=directory/sub/"result.png"
                if p.exists():
                    shutil.copyfile(p,screens/("exe-"+sub+".png"))
boundary=json.loads((OUT/"exe-boundary-result.json").read_text(encoding="utf-8"))
shutil.copyfile(Path(boundary["directory"])/"result.png",screens/"QA-006-exe-active-timer-stopped.png")
exe_dir=ROOT/"build"/("qa portable retest 031 "+uuid.uuid4().hex[:8])
exe_dir.mkdir()
exe=exe_dir/"AI-Tutor-0.3.1.exe"
shutil.copyfile(ROOT/"dist/AI-Tutor-0.3.1.exe",exe)
env={k:v for k,v in os.environ.items() if k!="QTWEBENGINE_REMOTE_DEBUGGING"}
r=subprocess.run([str(exe),"--smoke"],cwd=os.environ.get("WINDIR","C:/Windows"),env=env,capture_output=True,timeout=90)
shot=exe_dir/"app-data/cache/smoke.png"
if shot.exists():
    shutil.copyfile(shot,screens/"portable-smoke.png")
runs["portable"]={"exit":r.returncode,"screenshot":shot.exists(),"path":str(exe_dir),
                  "cwd":os.environ.get("WINDIR","C:/Windows"),"debug_endpoint":False,
                  "app_data_at_exe":(exe_dir/"app-data/data").is_dir()}
initial=json.loads((OUT/"environment.json").read_text(encoding="utf-8"))
runs["application_or_tests_changed"]=[p for p,h in initial["sha256"].items()
    if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
old=json.loads((ROOT/"docs/evidence/qa-fix-0.3.1/build-manifest.json").read_text(encoding="utf-8-sig"))
runs["release_manifest_source_mismatches"]=[p for p,h in old["source_sha256"].items()
    if hashlib.sha256((ROOT/p).read_bytes()).hexdigest().lower()!=h.lower()]
(OUT/"verification-summary.json").write_text(json.dumps(runs,indent=2,ensure_ascii=False),encoding="utf-8")
print(json.dumps({"portable":runs["portable"],"changed":runs["application_or_tests_changed"],
                 "release_source_mismatches":runs["release_manifest_source_mismatches"]}))
