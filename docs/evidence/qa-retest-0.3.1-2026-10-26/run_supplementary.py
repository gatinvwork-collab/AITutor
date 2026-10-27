import subprocess
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[3]
out=Path(__file__).resolve().parent
r=subprocess.run([sys.executable,"-X","utf8","-m","pytest",str(out/"test_supplementary.py"),"-q",
    "--basetemp=build/qa-retest031-supplementary","--junitxml="+str(out/"supplementary.xml")],
    cwd=root,capture_output=True,text=True,encoding="utf-8",errors="replace")
(out/"supplementary.log").write_text(r.stdout+r.stderr,encoding="utf-8")
print(r.stdout+r.stderr)
raise SystemExit(r.returncode)
