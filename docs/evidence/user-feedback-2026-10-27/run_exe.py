"""Launch only our identified synthetic installations; never user app-data."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from tests.exe_qa_031 import free_port,close_test_process

def main():
    mode=sys.argv[1] if len(sys.argv)>1 else 'full'
    suffix='-isolated' if mode=='isolated' else ''
    meta=json.loads((OUT/'environment.json').read_text(encoding='utf-8'))
    node=Path('C:/Users/591053/AppData/Local/JetBrains/PyCharm2026.2/acp-agents/.runtimes/node/24.19.0/node.exe')
    summary=[]
    for fixture in meta['fixtures']:
        port=free_port();exe=Path(fixture['exe']);start=time.monotonic()
        env={**os.environ,'QTWEBENGINE_REMOTE_DEBUGGING':f'127.0.0.1:{port}'}
        with (OUT/(fixture['label']+suffix+'-process.log')).open('wb') as log:
            startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
            process=subprocess.Popen([str(exe)],cwd=os.environ.get('WINDIR','C:/Windows'),env=env,
                                     stdout=log,stderr=log,startupinfo=startup)
            try:
                run=subprocess.run([str(node),str(OUT/'navigation.mjs'),str(port),str(OUT/'environment.json'),
                    fixture['label'],str(OUT/(fixture['label']+suffix+'-navigation.json')),mode],
                    capture_output=True,timeout=360)
                (OUT/(fixture['label']+suffix+'-runner.log')).write_bytes(run.stdout+run.stderr)
                summary.append({'fixture':fixture['label'],'exit':run.returncode,'wall_seconds':time.monotonic()-start})
            finally:
                close_test_process(process,exe)
        (OUT/('exe-runs'+suffix+'.json')).write_text(json.dumps(summary,indent=2),encoding='utf-8')
        print(json.dumps(summary[-1]),flush=True)

if __name__=='__main__':
    main()
