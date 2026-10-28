"""Collect independent current-run artifacts and validate identity/links."""
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent

def parse_log(name):
 raw=(OUT/name).read_bytes()
 text=raw.decode("utf-16" if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else "utf-8-sig",errors="replace")
 values=[]
 for line in text.splitlines():
  try:
   values.append(json.loads(line))
  except ValueError:
   pass
 return values[-1]

manifest=json.loads((ROOT/"docs/evidence/qa-fix-0.5.0a4/manifest.json").read_text(encoding="utf-8-sig"))
hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in manifest["source_sha256"]}
mismatch=[p for p,h in hashes.items() if h!=manifest["source_sha256"][p]]
exe_hash=hashlib.sha256((ROOT/"dist/Tutor-AI-0.5.0a4.exe").read_bytes()).hexdigest()
gui={}
for item in json.loads((OUT/"gui-summary.json").read_text(encoding="utf-8")):
 name=item["module"]
 result=parse_log(name+".log")
 shutil.copy2(Path(result["directory"])/"result.json",OUT/(name+"-result.json"))
 gui[name]={**item,"passed":result["passed"],"checks":len(result.get("checks",[])),"captures":result.get("captures"),"folder":result["directory"]}
exe={}
for name in ("exe_learning_050","exe_qa_051","exe_qa_052","exe_fault_052","exe_qa_053"):
 result=parse_log(name+".log")
 shutil.copy2(Path(result["directory"])/"summary.json",OUT/(name+"-result.json"))
 exe[name]=result
 assert result.get("exe_sha256",result.get("sha256"))==exe_hash
shutil.copy2(Path(exe["exe_learning_050"]["directory"])/"upgrade/verification.json",OUT/"upgrade-041-native-result.json")
for name in ("student-work.png","parent-bank.png"):
 shutil.copy2(Path(gui["gui_learning_050"]["folder"])/name,OUT/name)
startup=json.loads((OUT/"startup-result.json").read_text(encoding="utf-8"))
shutil.copy2(startup["screenshot"],OUT/"startup.png")
upgrades={key:json.loads((OUT/("upgrade-"+key+"-native-result.json")).read_text(encoding="utf-8")) for key in ("a1","a2","a3")}
native=ET.parse(OUT/"pytest.xml").getroot().find("testsuite")
summary={"date":"2026-10-28","version":"0.5.0a4","python":sys.version,"platform":platform.platform(),
 "exe_sha256":exe_hash,"source_sha256":hashes,"release_source_mismatches":mismatch,
 "native":native.attrib,"gui":gui,"gui_structured_conditions":sum(r["checks"] for r in gui.values()),
 "exe_modules_passed":{name:r["passed"] for name,r in exe.items()},"fault":exe["exe_fault_052"],
 "intent_http_matches_journal":exe["exe_qa_052"]["http_matches_journal"],"dialogue":exe["exe_qa_053"],
 "previous_fixes":exe["exe_qa_051"]["edges"],"native_upgrades":upgrades,"startup":startup,
 "new_confirmed_bugs":[],"full_acceptance":False,"live_models_used":False,
 "disk_free_initial_D_bytes":648105984,"disk_free_final_D_bytes":shutil.disk_usage(ROOT).free,"broken_report_links":[]}
output=OUT/"summary.json"
output.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
for name in ("qa-report-0.5.0a4-retest-2026-10-28.md","qa-bug-register-0.5.0a4-retest-2026-10-28.md"):
 report=ROOT/"docs"/name
 if not report.exists():
  summary["broken_report_links"].append({"missing_report":name})
  continue
 for target in re.findall(r"\]\(([^)]+)\)",report.read_text(encoding="utf-8")):
  if not target.startswith(("http:","https:","#")) and not (report.parent/target.split("#")[0]).exists():
   summary["broken_report_links"].append({"report":name,"target":target})
output.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"native":native.attrib,"gui_conditions":summary["gui_structured_conditions"],
 "gui_passed":all(r["passed"] for r in gui.values()),"exe_passed":all(r["passed"] for r in exe.values()),
 "source_mismatches":mismatch,"broken_links":summary["broken_report_links"],"dialogue_preserved":exe["exe_qa_053"]["active_dialogue_preserved"],
 "startup_passed":startup["passed"]}))
assert not mismatch and exe_hash==manifest["sha256"]
assert all(r["passed"] and r["exit_code"]==0 for r in gui.values()) and all(r["passed"] for r in exe.values())
assert all(r["passed"] and r["source_unchanged"] for r in upgrades.values())
assert exe["exe_qa_053"]["active_dialogue_preserved"] and exe["exe_qa_052"]["http_matches_journal"]
assert startup["passed"] and startup["sha256"]==exe_hash
assert not summary["broken_report_links"]
