"""Rerun current source/Portable QA with isolated logs and synthetic data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
os.environ["PATH"]=r"C:\Users\591053\AppData\Local\JetBrains\PyCharm2026.2\acp-agents\.runtimes\node\24.19.0"+os.pathsep+os.environ["PATH"]
mode=sys.argv[1]
modules={
 "gui":["gui_smoke","gui_feedback_03","gui_qa_031","gui_qa_032","gui_import_032","gui_feedback_041","gui_transfer_040","gui_learning_050","gui_qa_051","gui_qa_052"],
 "exe":["exe_learning_050","exe_qa_051","exe_qa_052"],
 "dialogue":["exe_qa_053"],"fault":["exe_fault_052"],
}[mode]
results=[]
for name in modules:
 start=time.monotonic()
 with (OUT/(name+".log")).open("wb") as log:
  try:
   child=subprocess.run([sys.executable,"-X","utf8","-m","tests."+name],cwd=ROOT,stdout=log,stderr=log,
                        timeout=500 if mode=="dialogue" else (350 if mode=="fault" else 230))
   code=child.returncode
  except subprocess.TimeoutExpired:
   code="timeout"
 results.append({"module":name,"exit_code":code,"seconds":round(time.monotonic()-start,2)})
 (OUT/(mode+"-summary.json")).write_text(json.dumps(results,indent=2),encoding="utf-8")
 print(json.dumps(results[-1]),flush=True)
raise SystemExit(0 if all(r["exit_code"]==0 for r in results) else 1)
