import json
import os
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from tests.exe_qa_031 import free_port,close_test_process
fixture=json.loads((OUT/'environment.json').read_text(encoding='utf-8'))['fixtures'][0]
exe=Path(fixture['exe']);port=free_port()
startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
with (OUT/'keyboard-process.log').open('wb') as log:
    process=subprocess.Popen([str(exe)],cwd=os.environ.get('WINDIR','C:/Windows'),
        env={**os.environ,'QTWEBENGINE_REMOTE_DEBUGGING':f'127.0.0.1:{port}'},stdout=log,stderr=log,startupinfo=startup)
    try:
        node='C:/Users/591053/AppData/Local/JetBrains/PyCharm2026.2/acp-agents/.runtimes/node/24.19.0/node.exe'
        r=subprocess.run([node,str(OUT/'keyboard.mjs'),str(port),str(OUT/'environment.json'),str(OUT/'keyboard-result.json')],capture_output=True,timeout=90)
        (OUT/'keyboard-runner.log').write_bytes(r.stdout+r.stderr)
        print((r.stdout+r.stderr).decode('utf-8',errors='replace'))
    finally:
        close_test_process(process,exe)
