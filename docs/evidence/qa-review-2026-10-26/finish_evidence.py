import json
import shutil
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
for source, target in [
    ("build/gui03-6da20ad5/result.json", "gui-feedback-03-result.json"),
    ("build/gui-120bd855/result.json", "gui-smoke-result.json")]:
    p = ROOT / source
    if p.exists():
        shutil.copyfile(p, OUT / target)
images = OUT / "screenshots"
images.mkdir(exist_ok=True)
for p in (ROOT / "build/gui03-6da20ad5").glob("*.png"):
    shutil.copyfile(p, images / p.name)
gui = json.loads((OUT/"gui_exploratory.log").read_text(encoding="utf-8").strip().splitlines()[-1])
shutil.copyfile(Path(gui["directory"]) / "cached-report-after-restore.png",
                images / "QA-001-cached-report-after-restore.png")
node = shutil.which("node")
checks = []
if node:
    for path in ("ui/app.js", "ui/profiles.js", "ui/addresses.js"):
        r = subprocess.run([node, "--check", path], cwd=ROOT, capture_output=True, text=True)
        checks.append({"path": path, "returncode": r.returncode, "output": r.stdout+r.stderr})
else:
    checks.append({"status": "blocked", "reason": "node executable unavailable"})
portable = ROOT / "build" / ("qa-portable-" + uuid.uuid4().hex[:8])
portable.mkdir()
shutil.copyfile(ROOT / "dist/AI-Tutor-0.3.exe", portable / "AI-Tutor-0.3.exe")
try:
    r = subprocess.run([str(portable / "AI-Tutor-0.3.exe"), "--smoke"], cwd=ROOT,
                       capture_output=True, timeout=90)
    smoke = portable / "app-data/cache/smoke.png"
    result = {"directory": str(portable), "returncode": r.returncode,
              "screenshot_exists": smoke.exists(),
              "data_next_to_exe": (portable/"app-data/data").is_dir(),
              "different_cwd": str(ROOT), "stderr": r.stderr.decode("utf-8", errors="replace")}
    if smoke.exists():
        shutil.copyfile(smoke, images / "portable-smoke.png")
except subprocess.TimeoutExpired:
    result = {"directory": str(portable), "status": "blocked", "reason": "90s timeout"}
(OUT/"supplementary.json").write_text(json.dumps({"javascript": checks, "portable": result},
    indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({"javascript": checks, "portable": result}, ensure_ascii=False))
