import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
root=Path(__file__).resolve().parents[3]
out=Path(__file__).resolve().parent
initial=json.loads((out/"environment.json").read_text(encoding="utf-8"))
changed=[p for p,h in initial["sha256"].items()
         if hashlib.sha256((root/p).read_bytes()).hexdigest()!=h]
broken=[]
reports=["qa-report-0.3.1-retest-2026-10-26.md","qa-bug-register-0.3.1-retest-2026-10-26.md"]
for name in reports:
    p=root/"docs"/name
    for link in re.findall(r"\]\(([^)]+)\)",p.read_text(encoding="utf-8")):
        if not (p.parent/link.split("#")[0]).exists():
            broken.append({"file":name,"link":link})
totals={"tests":0,"failures":0,"errors":0,"skipped":0}
for name in ("native.xml","original-independent-native.xml","extended.xml","supplementary.xml"):
    xml=ET.parse(out/name).getroot()
    for suite in xml.iter("testsuite"):
        for key in totals:
            totals[key]+=int(suite.attrib.get(key,0))
data={"unchanged_product_and_tests":not changed,"changed":changed,"broken_links":broken,
      "pytest":totals,"screenshots":len(list((out/"screenshots").glob("*.png"))),
      "qa_source_sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob("*.py")}}
(out/"artifact-verification.json").write_text(json.dumps(data,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in data.items() if k!="qa_source_sha256"}))
assert not changed and not broken and totals=={"tests":145,"failures":4,"errors":0,"skipped":0}
