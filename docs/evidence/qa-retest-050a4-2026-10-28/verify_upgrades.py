"""Current runtime against fresh copies of genuine previous-version fixtures."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from tests.upgrade_051 import verify

results=[]
for label,relative in (("a1","build/qa051-a1-source-final"),("a2","build/qa052-a2-source"),("a3","build/qa053-a3-source")):
 source=ROOT/relative
 assert shutil.disk_usage(ROOT).free>50*1024**2
 before=hashlib.sha256((source/"app-data/data/vault.aead").read_bytes()).hexdigest()
 target=ROOT/"build"/("qa-a4-upgrade-"+label+"-"+uuid.uuid4().hex[:8])
 target.mkdir()
 shutil.copytree(source/"app-data",target/"app-data")
 shutil.copy2(source/"expected.json",target/"expected.json")
 code=verify(target)
 value=json.loads((target/"verification.json").read_text(encoding="utf-8"))
 value.update(target=str(target),exit_code=code,source_unchanged=before==hashlib.sha256((source/"app-data/data/vault.aead").read_bytes()).hexdigest())
 (OUT/("upgrade-"+label+"-native-result.json")).write_text(json.dumps(value,indent=2),encoding="utf-8")
 results.append(value)
print(json.dumps({"passed":all(r["passed"] and r["source_unchanged"] for r in results),"sources":[r["source_version"] for r in results]}))
raise SystemExit(0 if all(r["passed"] and r["source_unchanged"] for r in results) else 1)
