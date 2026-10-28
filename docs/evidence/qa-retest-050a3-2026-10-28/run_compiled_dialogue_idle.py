"""Real-clock active dialogue on an isolated exe; no product clock overrides."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from tests.exe_qa_031 import free_port, close_test_process

os.environ["PATH"] = r"C:\Users\591053\AppData\Local\JetBrains\PyCharm2026.2\acp-agents\.runtimes\node\24.19.0" + os.pathsep + os.environ["PATH"]
class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        raw=json.dumps({"message":{"content":"Synthetic answer"},"prompt_eval_count":1,"eval_count":1}).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self,*_):
        pass

folder=ROOT/"build"/("qa-a3-dialogue-idle-"+uuid.uuid4().hex[:8])
folder.mkdir()
source=ROOT/"dist/Tutor-AI-0.5.0a3.exe"
exe=folder/source.name
os.link(source,exe)
(folder/"case.js").write_text((OUT/"compiled_dialogue_idle.js").read_text(encoding="utf-8"),encoding="utf-8")
(folder/"runner.mjs").write_text((ROOT/"tests/exe_cdp_runner.mjs").read_text(encoding="utf-8").replace("n<900","n<2400"),encoding="utf-8")
server=ThreadingHTTPServer(("127.0.0.1",0),Stub)
threading.Thread(target=server.serve_forever,daemon=True).start()
port=free_port()
startup=subprocess.STARTUPINFO()
startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow=0
env={**os.environ,"QTWEBENGINE_REMOTE_DEBUGGING":f"127.0.0.1:{port}"}
try:
    with (folder/"process.log").open("wb") as log:
        process=subprocess.Popen([str(exe)],cwd=os.environ.get("WINDIR","C:/Windows"),env=env,stdout=log,stderr=log,startupinfo=startup)
        try:
            done=subprocess.run(["node",str(folder/"runner.mjs"),str(port),str(folder/"case.js"),str(folder/"result.json"),
                                 f"http://127.0.0.1:{server.server_port}"],capture_output=True,timeout=280)
            (folder/"runner.log").write_bytes(done.stdout+done.stderr)
        finally:
            close_test_process(process,exe)
    result=json.loads((folder/"result.json").read_text(encoding="utf-8"))
    result.update(folder=str(folder),sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    (OUT/"compiled-dialogue-idle-result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False),flush=True)
finally:
    server.shutdown()
    server.server_close()
