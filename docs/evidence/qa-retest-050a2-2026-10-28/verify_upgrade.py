"""Retry isolated native a1 upgrade on writable C: after D: guard refusal."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from tests.upgrade_051 import verify

source = ROOT / "build/qa051-a1-source-final"
destination_root = Path(r"C:\Users\591053\AppData\Local\JetBrains\PyCharm2026.2\aia\agents\views\codex")
assert destination_root.is_dir() and shutil.disk_usage(destination_root).free > 100 * 1024**2
target = destination_root / ("qa-retest-a2-upgrade-" + uuid.uuid4().hex[:8])
assert target.resolve().is_relative_to(destination_root.resolve())
before = hashlib.sha256((source / "app-data/data/vault.aead").read_bytes()).hexdigest()
target.mkdir()
shutil.copytree(source / "app-data", target / "app-data")
shutil.copy2(source / "expected.json", target / "expected.json")
code = verify(target)
verification = json.loads((target / "verification.json").read_text(encoding="utf-8"))
verification.update(target=str(target), source_unchanged=before == hashlib.sha256(
    (source / "app-data/data/vault.aead").read_bytes()).hexdigest())
(OUT / "upgrade-a1-native-summary.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")
print(json.dumps(verification))
raise SystemExit(code if verification["source_unchanged"] else 1)
