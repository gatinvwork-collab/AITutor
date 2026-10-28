"""Form-selected intent versus actual loopback HTTP payload on the frozen exe."""

import hashlib
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tests.exe_qa_031 import ROOT, run_case
from tutor_ai import __version__


def main():
    output = ROOT / "build" / ("exe-intent052-" + uuid.uuid4().hex[:8])
    output.mkdir()
    sent = []

    class Stub(BaseHTTPRequestHandler):
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            sent.append(data["messages"])
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
    exe = ROOT / "dist" / f"Tutor-AI-{__version__}.exe"
    try:
        result = run_case(output, (ROOT / "tests/gui_qa_052.js").read_text(encoding="utf-8"),
                          f"http://127.0.0.1:{server.server_port}", exe, prefer_link=True)
        result["http_matches_journal"] = sent == [p["messages"] for p in result.get("payloads", [])] and len(sent) == 12
        result["passed"] = result["passed"] and result["http_matches_journal"]
        result["sha256"] = hashlib.sha256(exe.read_bytes()).hexdigest()
        (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"directory": str(output), **{k: v for k, v in result.items() if k != "payloads"}}, ensure_ascii=False))
        return 0 if result["passed"] else 1
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
