import json
import os
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from tests.exe_qa_031 import free_port
fixture=json.loads((OUT/'environment.json').read_text(encoding='utf-8'))['fixtures'][0]
port=free_port()
with (OUT/'manual-process.log').open('wb') as log:
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=1
    process=subprocess.Popen([fixture['exe']],cwd=os.environ.get('WINDIR','C:/Windows'),
        env={**os.environ,'QTWEBENGINE_REMOTE_DEBUGGING':f'127.0.0.1:{port}'},stdout=log,stderr=log,startupinfo=startup)
    node='C:/Users/591053/AppData/Local/JetBrains/PyCharm2026.2/acp-agents/.runtimes/node/24.19.0/node.exe'
    helper=subprocess.Popen([node,str(OUT/'manual_observer.mjs'),str(port),str(OUT/'environment.json'),str(OUT/'native-windows-clicks.json')],stdout=log,stderr=log)
    print(json.dumps({'launched_test_pid':process.pid,'port':port}),flush=True)
    process.wait(timeout=240)
    try:
        helper.wait(timeout=10)
    except subprocess.TimeoutExpired:
        helper.terminate()
