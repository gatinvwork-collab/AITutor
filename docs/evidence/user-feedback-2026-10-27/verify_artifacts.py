import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
meta=json.loads((OUT/'environment.json').read_text(encoding='utf-8'))
changed=[p for p,h in meta['sha256'].items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
rows=[]
for label in ('small','history1500'):
    for suffix in ('','-isolated'):
        data=json.loads((OUT/(label+suffix+'-navigation.json')).read_text(encoding='utf-8'))
        assert data['passed'] and not data['errors']
        rows.extend(data['clicks'])
keyboard=json.loads((OUT/'keyboard-result.json').read_text(encoding='utf-8'))
assert len(keyboard)==4
assert all(x['before']['focused']=='students' and x['after']['route']=='students'
           and x['after']['tag']=='BODY' for x in keyboard)
native=json.loads((OUT/'native-windows-clicks.json').read_text(encoding='utf-8'))
assert [x['requested'] for x in native['clicks']]==['notifications','home','students']
assert all(x['requested']==x['route'] for x in native['clicks'])
xml=ET.parse(OUT/'transfer.xml').getroot()
counts={k:sum(int(s.attrib.get(k,0)) for s in xml.iter('testsuite')) for k in ('tests','failures','errors','skipped')}
broken=[]
reports=['docs/qa-user-feedback-2026-10-27.md','docs/qa-user-feedback-register-2026-10-27.md',
         'docs/user-feedback-requirements-2026-10-27.md']
for name in reports:
    p=ROOT/name
    for link in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
        if re.match(r'https?://',link):
            continue
        target=link.split('#')[0]
        if target and not (p.parent/target).exists():
            broken.append({'file':name,'target':link})
result={'automated_pointer_checks':len(rows),'wrong_dom_routes':sum(not r['correct'] for r in rows),
        'trusted_clicks':all(r['trusted'] for r in rows),'windows_clicks':len(native['clicks']),
        'focus_loss_reproductions':len(keyboard),'transfer':counts,'changed_product':changed,
        'broken_links':broken,'capture_mismatch_needs_independent_verification':True,
        'qa_sources_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in OUT.iterdir() if p.suffix in ('.py','.mjs')}}
(OUT/'artifact-verification.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='qa_sources_sha256'},ensure_ascii=False))
assert not changed and not broken and len(rows)==1348 and counts=={'tests':29,'failures':0,'errors':0,'skipped':0}
