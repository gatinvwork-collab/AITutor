"""Ordinary frozen startup from another working directory, no DevTools."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
source=ROOT/"dist/Tutor-AI-0.5.0a4.exe"
folder=ROOT/"build"/("qa-a4-startup-"+uuid.uuid4().hex[:8])
folder.mkdir()
exe=folder/source.name
os.link(source,exe)
env=os.environ.copy()
env.pop("QTWEBENGINE_REMOTE_DEBUGGING",None)
startup=subprocess.STARTUPINFO()
startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow=0
with (folder/"process.log").open("wb") as log:
 process=subprocess.run([str(exe),"--smoke"],cwd=os.environ.get("WINDIR","C:/Windows"),env=env,
                        stdout=log,stderr=log,startupinfo=startup,timeout=100)
shot=folder/"app-data/cache/smoke.png"
result={"passed":process.returncode==0 and shot.exists() and shot.stat().st_size>0,
        "exit_code":process.returncode,"folder":str(folder),"screenshot":str(shot),
        "data_beside_exe":(folder/"app-data").is_dir(),"cwd":os.environ.get("WINDIR","C:/Windows"),
        "devtools_enabled":False,"sha256":hashlib.sha256(source.read_bytes()).hexdigest()}
(OUT/"startup-result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps(result),flush=True)
raise SystemExit(0 if result["passed"] else 1)
