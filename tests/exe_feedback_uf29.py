"""Exercise the UF29 route, policy, developer and input contract in the frozen exe."""

import hashlib
import json
import uuid
from pathlib import Path

from tutor_ai import __version__
from tests.exe_qa_031 import ROOT, run_case


def main():
    output = ROOT / "build" / ("exe-uf29-" + uuid.uuid4().hex[:8])
    output.mkdir()
    exe = ROOT / "dist" / f"Tutor-AI-{__version__}.exe"
    script = Path(__file__).with_name("gui_feedback_uf29.js").read_text(encoding="utf-8")
    script = script.replace("window.__capture='uf29-homework';await until(()=>window.__captured==='uf29-homework');", "")
    result = run_case(output, script, executable=exe, prefer_link=True)
    result["exe_sha256"] = hashlib.sha256(exe.read_bytes()).hexdigest()
    (output / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), **result}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
