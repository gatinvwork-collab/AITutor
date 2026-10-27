import ctypes
import hashlib
import json
import math
import statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent

def stats(values):
    ordered=sorted(values)
    return {'n':len(values),'median_ms':round(statistics.median(values),3),
            'p95_ms':round(ordered[math.ceil(.95*len(ordered))-1],3),
            'max_ms':round(max(values),3)}

def main():
    metadata=json.loads((OUT/'environment.json').read_text(encoding='utf-8'))
    result={'fixtures':{},'unchanged_product':True,'changed_product':[]}
    for fixture in metadata['fixtures']:
        p=OUT/(fixture['label']+'-navigation.json')
        if not p.exists():
            continue
        raw=json.loads(p.read_text(encoding='utf-8'))
        entry={'viewport':raw['viewport'],'parent_login_ms':raw['parent_login_ms'],
               'click_count':len(raw['clicks']),'wrong_routes':[x for x in raw['clicks'] if not x['correct']],
               'all_clicks_trusted':all(x.get('trusted') for x in raw['clicks']),
               'errors':raw['errors'],'keyboard':raw['keyboard'],'metrics':[],'rpc':[]}
        for design in ('strict','modern'):
            for route in ('notifications','home','students'):
                rows=[x for x in raw['clicks'] if x.get('design')==design and x['requested']==route
                      and 'iteration' in x and x.get('role')=='PARENT']
                entry['metrics'].append({'design':design,'route':route,
                    'click_to_double_raf':stats([x['elapsed_ms'] for x in rows]),
                    'driver_roundtrip_including_poll':stats([x['driver_elapsed_ms'] for x in rows]),
                    'synchronous_render':stats([x['render_ms'] for x in rows])})
        for command in ('status','snapshot'):
            entry['rpc'].append({'command':command,**stats([x['ms'] for x in raw['rpc'] if x['command']==command])})
        result['fixtures'][fixture['label']]=entry
    for p,h in metadata['sha256'].items():
        if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h:
            result['unchanged_product']=False
            result['changed_product'].append(p)
    class Memory(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),*[(n,ctypes.c_ulonglong) for n in
            ('total_physical','available_physical','total_page','available_page','total_virtual','available_virtual','extended')]]
    m=Memory();m.length=ctypes.sizeof(m)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        result['memory_at_summary']={k:getattr(m,k) for k in ('load','total_physical','available_physical')}
    (OUT/'metrics.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__=='__main__':
    main()
