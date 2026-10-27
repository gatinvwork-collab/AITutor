import subprocess
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[3]
out=Path(__file__).resolve().parent
r=subprocess.run([sys.executable,"-X","utf8","-m","pytest",str(out/"test_independent_032.py"),"-q",
    "--basetemp=build/qa-retest032-independent","--junitxml="+str(out/"independent.xml")],
    cwd=root,capture_output=True,text=True,encoding="utf-8",errors="replace")
(out/"independent.log").write_text(r.stdout+r.stderr,encoding="utf-8")
print(r.stdout+r.stderr)
raise SystemExit(r.returncode)
