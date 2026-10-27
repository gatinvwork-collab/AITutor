import json
import shutil
from pathlib import Path
root = Path(__file__).resolve().parents[3]
out = Path(__file__).resolve().parent
source = root / "build/qa-review-gui-52b7ac69"
shutil.copyfile(source/"result.json", out/"gui-exploratory-result.json")
shutil.copyfile(source/"cached-report-after-restore.png",
                out/"screenshots/QA-001-cached-report-after-restore.png")
result = json.loads((out/"gui-exploratory-result.json").read_text(encoding="utf-8"))
print(json.dumps({"checks": len(result["checks"]), "passed": sum(c["passed"] for c in result["checks"]),
                  "failed": sum(not c["passed"] for c in result["checks"])}, ensure_ascii=False))
