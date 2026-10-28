"""Collect nonsecret QA results and verify against the release source manifest."""
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

def read(path):
    raw = path.read_bytes()
    return raw.decode("utf-16" if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else "utf-8-sig", errors="replace")

def result(log):
    values = []
    for line in read(OUT / log).splitlines():
        try:
            values.append(json.loads(line))
        except ValueError:
            pass
    return values[-1]

release = json.loads((ROOT / "docs/evidence/learning-0.5.0a1/manifest.json").read_text(encoding="utf-8-sig"))
hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in release["source_sha256"]}
mismatches = [p for p, h in hashes.items() if h != release["source_sha256"][p]]
packaged = result("exe-learning-final.log")
shutil.copy2(Path(packaged["directory"]) / "summary.json", OUT / "exe-summary.json")
edge = json.loads((OUT / "compiled-edges-result.json").read_text(encoding="utf-8"))
if "folder" not in edge:
    # Recover metadata from the already written summary of this same run.
    edge = {"folder": json.loads((OUT / "summary.json").read_text(encoding="utf-8"))["compiled_defects"]["folder"], **edge}
    (OUT / "compiled-edges-result.json").write_text(json.dumps(edge, indent=2), encoding="utf-8")
for name in ("result.json", "result.png"):
    shutil.copy2(Path(edge["folder"]) / name, OUT / ("compiled-edges-raw-" + name))
ui = {}
for log in ["ide-gui-feedback03-final.log", "gui_qa_031.log", "gui_qa_032.log", "gui_feedback_041.log",
            "ide-gui-learning.log", "gui-current-homework.log", "gui-transfer-current.log"]:
    item = result(log)
    ui[log] = {"passed": item["passed"], "checks": len(item.get("checks", [])), "folder": item["directory"]}
    shutil.copy2(Path(item["directory"]) / "result.json", OUT / (log.removesuffix(".log") + "-result.json"))
for name in ("parent-bank.png", "student-work.png", "parent-review.png"):
    shutil.copy2(ROOT / "build/gui-learning050-07306c37" / name, OUT / name)
tests = ET.parse(OUT / "pytest.xml").getroot().find("testsuite")
edges = ET.parse(OUT / "independent.xml").getroot().find("testsuite")
summary = {
    "date": "2026-10-28", "version": "0.5.0a1", "python": sys.version,
    "platform": platform.platform(), "source_sha256": hashes,
    "release_source_mismatches": mismatches,
    "exe_sha256": hashlib.sha256((ROOT / "dist/Tutor-AI-0.5.0a1.exe").read_bytes()).hexdigest(),
    "native": tests.attrib, "independent_expected_behavior_tests": edges.attrib,
    "gui": ui, "packaged_workflow_checks": len(packaged["workflow"]["checks"]),
    "packaged_upgrade_ui_checks": len(packaged["upgrade_ui"]["checks"]),
    "packaged_upgrade_native_checks": 10, "packaged_passed": packaged["passed"],
    "source_fixture_unchanged": packaged["source_unchanged"], "compiled_defects": edge,
    "full_acceptance": False, "real_provider_requests": False,
    "free_disk_bytes_after": shutil.disk_usage(ROOT).free,
}
broken_links = []
for report_name in ("qa-report-0.5.0a1-2026-10-28.md", "qa-bug-register-0.5.0a1-2026-10-28.md"):
    report = ROOT / "docs" / report_name
    for target in re.findall(r"\]\(([^)]+)\)", report.read_text(encoding="utf-8")):
        if not target.startswith(("http:", "https:", "#")) and not (report.parent / target.split("#")[0]).exists():
            broken_links.append({"report": report_name, "target": target})
summary["broken_report_links"] = broken_links
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"native": tests.attrib, "independent": edges.attrib, "gui": ui,
                  "release_source_mismatches": mismatches, "packaged_passed": packaged["passed"]}, ensure_ascii=False))
assert not mismatches and summary["exe_sha256"] == release["sha256"]
assert packaged["passed"] and all(x["passed"] for x in ui.values())
assert not broken_links, broken_links
