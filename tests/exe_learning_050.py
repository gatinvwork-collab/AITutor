"""Actual Portable executable against a loopback synthetic model, plus 0.4.1 upgrade."""

import hashlib
import json
import re
import shutil
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tests.exe_qa_031 import run_case, ROOT
from tests.gui_learning_050 import DemoProvider
from tests.upgrade_050 import PASSWORD, verify
from tutor_ai import __version__


def main(executable=None, version=__version__):
    exe = Path(executable) if executable else ROOT / "dist" / f"Tutor-AI-{version}.exe"
    output = ROOT / "build" / ("exe-learning050-" + uuid.uuid4().hex[:8])
    output.mkdir()

    class Stub(BaseHTTPRequestHandler):
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            result = DemoProvider({}).send_message(data["messages"])
            raw = json.dumps(
                {"message": {"content": result["text"]}, "prompt_eval_count": 10, "eval_count": 10}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    case = output / "workflow"
    case.mkdir()
    script = Path(__file__).with_name("gui_learning_050.js").read_text(encoding="utf-8")
    script = re.sub(r"const shot=async name=>\{.*?\};", "const shot=async name=>{};", script)
    script = script.replace(
        "kind:'ollama',model:'synthetic-only',revision:0",
        "kind:'ollama',model:'synthetic-only',revision:0,endpoint:window.__qaEndpoint",
    )
    try:
        workflow = run_case(case, script, f"http://127.0.0.1:{server.server_port}", exe, prefer_link=True)
    finally:
        server.shutdown()
        server.server_close()

    fixture = ROOT / "build" / "upgrade050-final"
    before = (fixture / "app-data" / "data" / "vault.aead").read_bytes()
    upgrade = output / "upgrade"
    upgrade.mkdir()
    shutil.copytree(fixture / "app-data", upgrade / "app-data")
    shutil.copy2(fixture / "expected.json", upgrade / "expected.json")
    expected = json.loads((fixture / "expected.json").read_text(encoding="utf-8"))
    upgrade_script = """(async()=>{const checks=[];try{const check=(name,ok)=>{checks.push({name,ok:!!ok});if(!ok)throw Error(name);};
      await rpc('login',{account:PARENT,password:PASSWORD});await refresh();
      check('version',(await rpc('status')).version==='0.5.0a1');
      check('linked children',state.data.students.length>=1);
      check('history preserved',state.data.students.some(s=>s.sessions.some(x=>x.id==='past'&&x.seconds===121)));
      navigate('learning');await learnRefresh();render();
      check('legacy not confirmed',learnData().map.every(t=>!t.confirmed));
      check('schema upgrade screen',!!document.querySelector('[data-learning-form="assignment"]'));
      window.__testResult={passed:true,checks};
    }catch(error){window.__testResult={passed:false,error:error.message,checks};}})();"""
    upgrade_script = upgrade_script.replace("PARENT", json.dumps(expected["parent"])).replace(
        "PASSWORD", json.dumps(PASSWORD)
    ).replace('0.5.0a1', version)
    upgrade_ui = run_case(upgrade, upgrade_script, executable=exe, prefer_link=True)
    verification = verify(upgrade) == 0
    result = {
        "passed": workflow["passed"] and upgrade_ui["passed"] and verification,
        "exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
        "workflow": workflow,
        "upgrade_ui": upgrade_ui,
        "upgrade_native": verification,
        "source_unchanged": (fixture / "app-data" / "data" / "vault.aead").read_bytes() == before,
        "network": "loopback synthetic server only; no live AI/OCR quality claim",
    }
    result["passed"] = result["passed"] and result["source_unchanged"]
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"directory": str(output), **result}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
