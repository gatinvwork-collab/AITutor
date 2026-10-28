"""Collect final nonsecret QA artifacts; validate identity and report links."""
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent

def parse_log(name):
    raw = (OUT / name).read_bytes()
    text = raw.decode("utf-16" if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else "utf-8-sig", errors="replace")
    values = []
    for line in text.splitlines():
        try:
            values.append(json.loads(line))
        except ValueError:
            pass
    return values[-1]

release = json.loads((ROOT / "docs/evidence/qa-fix-0.5.0a2/manifest.json").read_text(encoding="utf-8-sig"))
hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in release["source_sha256"]}
mismatch = [p for p,h in hashes.items() if h != release["source_sha256"][p]]
gui = {}
for item in json.loads((OUT / "gui-summary.json").read_text(encoding="utf-8")):
    name = item["module"]
    result = parse_log(name + ".log")
    shutil.copy2(Path(result["directory"]) / "result.json", OUT / (name + "-result.json"))
    gui[name] = {**item, "passed": result["passed"], "checks": len(result.get("checks", [])),
                 "captures": result.get("captures"), "folder": result["directory"]}
general = parse_log("exe_learning_050.log")
targeted = parse_log("exe_qa_051.log")
for name,value in (("exe-general",general),("exe-targeted",targeted)):
    shutil.copy2(Path(value["directory"]) / "summary.json", OUT / (name + "-result.json"))
shutil.copy2(Path(general["directory"]) / "upgrade/verification.json", OUT / "upgrade-041-native-result.json")
for name in ("compiled-intent", "compiled-copy"):
    value = json.loads((OUT / (name + "-result.json")).read_text(encoding="utf-8"))
    assert value["passed"]
    shutil.copy2(Path(value["folder"]) / "result.png", OUT / (name + ".png"))
for name in ("parent-bank.png", "student-work.png"):
    shutil.copy2(Path(gui["gui_learning_050"]["folder"]) / name, OUT / name)
upgrade = json.loads((OUT / "upgrade-a1-native-summary.json").read_text(encoding="utf-8"))
native = ET.parse(OUT / "pytest.xml").getroot().find("testsuite")
extra = ET.parse(OUT / "additional.xml").getroot().find("testsuite")
broken = []
for name in ("qa-report-0.5.0a2-retest-2026-10-28.md", "qa-bug-register-0.5.0a2-retest-2026-10-28.md"):
    report = ROOT / "docs" / name
    if report.exists():
        for target in re.findall(r"\]\(([^)]+)\)", report.read_text(encoding="utf-8")):
            if not target.startswith(("https:", "http:", "#")) and not (report.parent / target.split("#")[0]).exists():
                broken.append({"report": name, "target": target})
    else:
        broken.append({"report": name, "missing": True})
summary = {
    "date": "2026-10-28", "version": "0.5.0a2", "platform": platform.platform(), "python": sys.version,
    "exe_sha256": hashlib.sha256((ROOT / "dist/Tutor-AI-0.5.0a2.exe").read_bytes()).hexdigest(),
    "source_sha256": hashes, "release_source_mismatches": mismatch,
    "native": native.attrib, "additional_expected_behavior_tests": extra.attrib,
    "gui": gui, "gui_structured_conditions": sum(x["checks"] for x in gui.values()),
    "compiled_general_passed": general["passed"], "compiled_targeted_passed": targeted["passed"],
    "previous_bug_witnesses": targeted["edges"], "upgrade_a1_native": upgrade,
    "source_a1_unchanged": targeted["source_a1_unchanged"], "source_041_unchanged": general["source_unchanged"],
    "new_bugs": ["QA-050-04", "QA-050-05"], "live_ai_used": False, "full_acceptance": False,
    "disk_free_initial_D_bytes": 227340288, "disk_free_final_D_bytes": shutil.disk_usage(ROOT).free,
    "guarded_upgrade_attempt": "D: insufficient space, no verification run; repeated successfully on writable C:",
    "broken_report_links": broken,
}
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"native": native.attrib,"additional":extra.attrib,"gui_passed":all(x["passed"] for x in gui.values()),
                  "gui_conditions":summary["gui_structured_conditions"],"exe_passed":general["passed"] and targeted["passed"],
                  "source_mismatches":mismatch,"broken_links":broken,"upgrade_a1_passed":upgrade["passed"]}))
assert not mismatch and summary["exe_sha256"] == release["sha256"]
assert general["passed"] and targeted["passed"] and upgrade["passed"] and upgrade["source_unchanged"]
assert all(x["passed"] and x["exit_code"]==0 for x in gui.values())
assert not broken, broken
