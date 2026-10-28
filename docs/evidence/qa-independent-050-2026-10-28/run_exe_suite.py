"""Existing packaged workflow/upgrade, then independent UI regressions."""
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
sys.path.insert(0, str(ROOT))
os.environ["PATH"] = str(Path(r"C:\Users\591053\AppData\Local\JetBrains\PyCharm2026.2\acp-agents\.runtimes\node\24.19.0")) + os.pathsep + os.environ["PATH"]
if "--edges-only" not in sys.argv:
    with (OUT / "exe-learning-final.log").open("wb") as log:
        run = subprocess.run([sys.executable, "-X", "utf8", "-m", "tests.exe_learning_050"], cwd=ROOT,
                             stdout=log, stderr=log, timeout=360)
    print(json.dumps({"packaged_workflow_exit": run.returncode}), flush=True)
from tests.exe_qa_031 import run_case
from tests.gui_learning_050 import DemoProvider

class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        result = DemoProvider({}).send_message(data["messages"])
        raw = json.dumps({"message": {"content": result["text"]}, "prompt_eval_count": 10, "eval_count": 10}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_):
        pass

server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
threading.Thread(target=server.serve_forever, daemon=True).start()
folder = ROOT / "build" / ("qa-independent-exe050-" + uuid.uuid4().hex[:8])
folder.mkdir()
try:
    result = run_case(folder, (OUT / "compiled_edges.js").read_text(encoding="utf-8"),
                      f"http://127.0.0.1:{server.server_port}", ROOT / "dist/Tutor-AI-0.5.0a1.exe", prefer_link=True)
    (OUT / "compiled-edges-result.json").write_text(json.dumps({"folder": str(folder), **result}, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
finally:
    server.shutdown()
    server.server_close()
