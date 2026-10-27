"""Run unchanged exe acceptance with an equivalent Qt CDP transport."""
import contextlib
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from tests import exe_qa_031
original_run=subprocess.run
def run(args,*positional,**kwargs):
    if isinstance(args,list) and args[0]=="node":
        args=[sys.executable,"-X","utf8",str(OUT/"cdp_qt.py"),*args[2:]]
    return original_run(args,*positional,**kwargs)
subprocess.run=run
with (OUT/"exe.log").open("w",encoding="utf-8") as log:
    with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
        result=exe_qa_031.main()
print((OUT/"exe.log").read_text(encoding="utf-8"))
raise SystemExit(result)
