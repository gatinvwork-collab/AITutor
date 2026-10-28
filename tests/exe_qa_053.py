"""Real-clock dialogue and genuine idle on a Portable copy; loopback only."""

import hashlib
import json
import os
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tutor_ai import __version__
from tests.exe_qa_031 import ROOT, free_port, close_test_process


def main():
    folder = ROOT / "build" / ("exe-dialogue053-" + uuid.uuid4().hex[:8])
    folder.mkdir()
    source = ROOT / "dist" / f"Tutor-AI-{__version__}.exe"
    exe = folder / source.name
    os.link(source, exe)
    (folder / "case.js").write_text((ROOT / "tests/gui_qa_053.js").read_text(encoding="utf-8"), encoding="utf-8")
    runner = (ROOT / "tests/exe_cdp_runner.mjs").read_text(encoding="utf-8").replace("n<900", "n<4000")
    (folder / "runner.mjs").write_text(runner, encoding="utf-8")

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

    server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = free_port()
    env = {**os.environ, "QTWEBENGINE_REMOTE_DEBUGGING": f"127.0.0.1:{port}"}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    try:
        with (folder / "process.log").open("wb") as log:
            process = subprocess.Popen([str(exe)], cwd=os.environ.get("WINDIR", "C:/Windows"), env=env,
                                       stdout=log, stderr=log, startupinfo=startup)
            try:
                done = subprocess.run(["node", str(folder / "runner.mjs"), str(port), str(folder / "case.js"),
                                       str(folder / "result.json"), f"http://127.0.0.1:{server.server_port}"],
                                      capture_output=True, timeout=440)
                (folder / "runner.log").write_bytes(done.stdout + done.stderr)
            finally:
                close_test_process(process, exe)
        result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        result["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        (folder / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"directory": str(folder), **result}))
        return 0 if done.returncode == 0 and result["passed"] and result.get("active_dialogue_preserved") else 1
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
