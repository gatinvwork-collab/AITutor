"""Reproduce intent loss on a frozen exe with a loopback stub, only synthetic data."""
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ["PATH"] = r"C:\Users\591053\AppData\Local\JetBrains\PyCharm2026.2\acp-agents\.runtimes\node\24.19.0" + os.pathsep + os.environ["PATH"]
from tests.exe_qa_031 import run_case

class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        raw = json.dumps({"message": {"content": "Synthetic answer"}, "prompt_eval_count": 1, "eval_count": 1}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_):
        pass

copy_mode = "--copy" in sys.argv
folder_root = Path(r"C:\Users\591053\AppData\Local\JetBrains\PyCharm2026.2\aia\agents\views\codex") if copy_mode else ROOT / "build"
folder = folder_root / ("qa-a2-copy-" if copy_mode else "qa-a2-intent-")
folder = folder.with_name(folder.name + uuid.uuid4().hex[:8])
folder.mkdir()
exe = ROOT / "dist/Tutor-AI-0.5.0a2.exe"
server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    result = run_case(folder, (OUT / ("compiled_copy.js" if copy_mode else "compiled_intent.js")).read_text(encoding="utf-8"),
                      f"http://127.0.0.1:{server.server_port}", exe, prefer_link=True)
    result.update(folder=str(folder), sha256=hashlib.sha256(exe.read_bytes()).hexdigest())
    (OUT / ("compiled-copy-result.json" if copy_mode else "compiled-intent-result.json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!='payloads'}), flush=True)
finally:
    server.shutdown()
    server.server_close()
