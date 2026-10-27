"""Full 0.3.2 exe: timer + legacy import boundary + earlier fixed defects."""
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from aitutor.service import Service
from tests.exe_qa_031 import ROOT, run_case, main as previous_regression
from tests.qa_fixtures import seed_import_032


def main():
    executable = ROOT / "dist" / "AI-Tutor-0.3.2.exe"
    output = ROOT / "build" / ("exe032-" + uuid.uuid4().hex[:8])
    output.mkdir()
    class Stub(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            raw = json.dumps({"message": {"role": "assistant", "content": "Учебное объяснение."},
                              "prompt_eval_count": 1, "eval_count": 1}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    timer = output / "timer"
    timer.mkdir()
    try:
        timer_result = run_case(timer, Path(__file__).with_name("gui_qa_032.js").read_text(encoding="utf-8"),
                                f"http://127.0.0.1:{server.server_port}", executable)
    finally:
        server.shutdown()
        server.server_close()
    imported = output / "import"
    imported.mkdir()
    service = Service(imported / "app-data")
    service.register("Import parent", "import-parent-password", "PARENT")
    child = service.register("Import child", "import-child-password", "STUDENT", {
        "region": "Region", "city": "City", "school": "School", "grade": 7, "address": {"mode": "manual"}})
    seed_import_032(service, child["id"])
    original_records = service.store.all("homework")
    service.logout()
    login = {"id": child["id"], "password": "import-child-password"}
    script = "window.__qaLogin=" + json.dumps(login) + ";\n" + Path(__file__).with_name("gui_import_032.js").read_text(encoding="utf-8")
    import_result = run_case(imported, script, executable=executable)
    service.login(child["id"], "import-child-password")
    unchanged = all(service.store.get("homework", old["id"]) == old for old in original_records)
    service.logout()
    prior_result = previous_regression(executable)
    summary = {"passed": timer_result["passed"] and import_result["passed"] and unchanged and prior_result == 0,
               "directory": str(output), "timer": timer_result, "import": import_result,
               "legacy_records_unchanged": unchanged, "previous_regression_exit": prior_result}
    (output / "result.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
