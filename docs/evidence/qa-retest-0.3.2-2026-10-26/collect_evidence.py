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
collected={}
for name in ("original-independent-gui","tests-gui_smoke","tests-gui_feedback_03",
             "tests-gui_qa_031","tests-gui_qa_032","tests-gui_import_032"):
    lines=(OUT/(name+".log")).read_text(encoding="utf-8").strip().splitlines()
    data=next((json.loads(s) for s in reversed(lines) if s.startswith("{")),None)
    assert data and data["passed"],name
    collected[name]=data
    (OUT/(name+"-result.json")).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
    directory=Path(data["directory"])
    if name=="tests-gui_feedback_03":
        for p in directory.glob("*.png"):
            shutil.copyfile(p,screens/p.name)
lines=(OUT/"exe.log").read_text(encoding="utf-8").splitlines()
exe_results=[json.loads(s) for s in lines if s.startswith("{")]
assert len(exe_results)==2 and all(r["passed"] for r in exe_results)
for data,name in zip(exe_results,("exe-prior-regression","exe032")):
    collected[name]=data
    (OUT/(name+"-result.json")).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
    directory=Path(data["directory"])
    for sub in ("workflow","historical","foreign-restore","timer","import"):
        p=directory/sub/"result.png"
        if p.exists():
            shutil.copyfile(p,screens/(name+"-"+sub+".png"))
portable=ROOT/"build"/("qa portable retest 032 "+uuid.uuid4().hex[:8])
portable.mkdir()
exe=portable/"AI-Tutor-0.3.2.exe"
shutil.copyfile(ROOT/"dist/AI-Tutor-0.3.2.exe",exe)
env={k:v for k,v in os.environ.items() if k!="QTWEBENGINE_REMOTE_DEBUGGING"}
r=subprocess.run([str(exe),"--smoke"],cwd=os.environ.get("WINDIR","C:/Windows"),env=env,
                 capture_output=True,timeout=90)
shot=portable/"app-data/cache/smoke.png"
if shot.exists():
    shutil.copyfile(shot,screens/"portable-smoke.png")
collected["portable"]={"exit":r.returncode,"screenshot":shot.exists(),"path":str(portable),
    "app_data_at_exe":(portable/"app-data/data").is_dir(),"cwd":os.environ.get("WINDIR","C:/Windows"),
    "debug_endpoint":False}
old=json.loads((ROOT/"docs/evidence/qa-fix-0.3.2/build-manifest.json").read_text(encoding="utf-8-sig"))
collected["release_manifest_mismatches"]=[p for p,h in old["source_sha256"].items()
    if hashlib.sha256((ROOT/p).read_bytes()).hexdigest().lower()!=h.lower()]
initial=json.loads((OUT/"environment.json").read_text(encoding="utf-8"))
collected["application_or_tests_changed"]=[p for p,h in initial["sha256"].items()
    if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
(OUT/"verification-summary.json").write_text(json.dumps(collected,indent=2,ensure_ascii=False),encoding="utf-8")
print(json.dumps({"portable":collected["portable"],"changed":collected["application_or_tests_changed"],
                 "release_mismatches":collected["release_manifest_mismatches"]}))
