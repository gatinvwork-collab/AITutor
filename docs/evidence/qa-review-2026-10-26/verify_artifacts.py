import hashlib
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[3]
out = Path(__file__).resolve().parent
manifest = json.loads((out/"environment-and-runs.json").read_text(encoding="utf-8"))
changed = [path for path, digest in manifest["sha256"].items()
           if hashlib.sha256((root/path).read_bytes()).hexdigest() != digest]
broken = []
for name in ("qa-report-2026-10-26.md", "qa-bug-register-2026-10-26.md"):
    path = root/"docs"/name
    for link in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
        if not (path.parent/link.split("#")[0]).exists():
            broken.append({"file": name, "link": link})
result = {"application_files_changed": changed, "broken_report_links": broken,
          "screenshots": len(list((out/"screenshots").glob("*.png")))}
(out/"artifact-verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result))
assert not changed and not broken
