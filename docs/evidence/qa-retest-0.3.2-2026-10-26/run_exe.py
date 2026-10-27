"""Run existing release scenarios against the actual 0.3.2 exe."""
import contextlib
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from tests import exe_qa_032
original_run=subprocess.run
def redirected(args,*positional,**kwargs):
    if isinstance(args,list) and args[0]=="node":
        transport=ROOT/"docs/evidence/qa-retest-0.3.1-2026-10-26/cdp_qt.py"
        args=[sys.executable,"-X","utf8",str(transport),*args[2:]]
    return original_run(args,*positional,**kwargs)
subprocess.run=redirected
with (OUT/"exe.log").open("w",encoding="utf-8") as log:
    with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
        result=exe_qa_032.main()
(OUT/"exe-exit.txt").write_text(str(result),encoding="utf-8")
print((OUT/"exe.log").read_text(encoding="utf-8"))
raise SystemExit(result)
