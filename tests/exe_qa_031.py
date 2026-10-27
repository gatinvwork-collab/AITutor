"""Acceptance of the actual frozen exe using isolated data and local HTTP only.

Qt's supported developer-tools endpoint is enabled only in the test child env.
No debug endpoint is enabled by application code or persisted in configuration.
"""
import ctypes
import json
import os
import shutil
import socket
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tutor_ai.service import Service
from tests.test_application import PASSWORD, PROFILE, CHILD_PASSWORD
from tests.qa_fixtures import foreign_backup

ROOT = Path(__file__).resolve().parent.parent


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def close_test_process(process, exe):
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                                 ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    ctypes.windll.user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    ctypes.windll.user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    def close(hwnd, _):
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel.OpenProcess(0x1000, False, pid.value)
        is_test_child = False
        if handle:
            path = ctypes.create_unicode_buffer(32768)
            size = ctypes.c_ulong(len(path))
            if kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                is_test_child = Path(path.value).resolve() == exe.resolve()
            kernel.CloseHandle(handle)
        if pid.value == process.pid or is_test_child:
            ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
        return True
    ctypes.windll.user32.EnumWindows(callback_type(close), 0)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=10)


def run_case(directory, script, endpoint="", executable=None, prefer_link=False):
    source = Path(executable) if executable else ROOT / "dist" / "AI-Tutor-0.3.1.exe"
    exe = directory / source.name
    if prefer_link:
        try:
            os.link(source, exe)
        except OSError:
            shutil.copy2(source, exe)
    else:
        shutil.copy2(source, exe)
    script_file = directory / "case.js"
    script_file.write_text(script, encoding="utf-8")
    result = directory / "result.json"
    port = free_port()
    env = {**os.environ, "QTWEBENGINE_REMOTE_DEBUGGING": f"127.0.0.1:{port}"}
    with (directory / "process.log").open("wb") as log:
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        process = subprocess.Popen([str(exe)], cwd=os.environ.get("WINDIR", "C:/Windows"), env=env,
                                   stdout=log, stderr=log, startupinfo=startup)
        try:
            completed = subprocess.run(["node", str(ROOT / "tests" / "exe_cdp_runner.mjs"), str(port),
                str(script_file), str(result), endpoint], capture_output=True, timeout=150)
            (directory / "runner.log").write_bytes(completed.stdout + completed.stderr)
            if completed.returncode:
                raise RuntimeError((completed.stdout + completed.stderr).decode("utf-8", errors="replace"))
            return json.loads(result.read_text(encoding="utf-8"))
        finally:
            close_test_process(process, exe)


def main(executable=None):
    output = ROOT / "build" / (("exe-regression-" if executable else "exe031-") + uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    workflow = output / "workflow"
    workflow.mkdir()
    class OllamaStub(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            raw = json.dumps({"message": {"role": "assistant", "content": "Разберём тему по шагам."},
                              "prompt_eval_count": 1, "eval_count": 1}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), OllamaStub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        workflow_result = run_case(workflow, (ROOT / "tests" / "gui_qa_031.js").read_text(encoding="utf-8"),
                                   f"http://127.0.0.1:{server.server_port}", executable)
    finally:
        server.shutdown()
        server.server_close()
    cross = output / "foreign-restore"
    cross.mkdir()
    shutil.copytree(workflow / "app-data", cross / "app-data")
    cross_service = Service(cross / "app-data")
    accounts = cross_service.status()["accounts"]
    owner = next(a["id"] for a in accounts if a["name"] == "QA031 Parent A")
    cross_service.login(owner, "qa031-parent-password")
    kid = next(a["id"] for a in accounts if a["role"] == "STUDENT")
    with cross_service.store.transaction():
        cross_service.store.put("session", "late-collision", {"id": "late-collision", "student": kid,
            "subject": "physics", "topic": "retired", "created": "2026-10-26", "status": "complete",
            "messages": [{"text": "CROSS-VAULT-PRIVATE"}], "title": "Private original report",
            "seconds": 0, "total": 0, "correct": 0, "program_snapshot": {}}, kid)
    name, _ = foreign_backup(cross_service, output / "foreign-fixture", {
        a["id"]: "qa031-child-password" if a["role"] == "STUDENT" else "qa031-parent-password"
        for a in accounts}, "qa031-backup-password")
    cross_service.logout()
    cross_script = """
(async()=>{try{
  const until=async fn=>{for(let n=0;n<300;n++){if(fn())return;await new Promise(r=>setTimeout(r,40));}throw Error('timeout');};
  await rpc('login',{account:ACCOUNT,password:'qa031-parent-password'});await refresh();state.route='history';render();
  document.querySelector('[data-action="open-session"][data-value="late-collision"]').click();await until(()=>!inFlight&&!!state.report);
  const oldContext=nativeContext;state.route='backup';render();const f=document.querySelector('form[data-form="restore"]');
  f.elements.filename.value=ARCHIVE;f.elements.password.value='qa031-backup-password';f.elements.account.value=ACCOUNT;
  f.elements.account_password.value='qa031-parent-password';f.querySelector('input[type="checkbox"]').checked=true;
  f.requestSubmit();await until(()=>!inFlight&&!state.data);
  const login=document.querySelector('form[data-form="login"]');login.elements.account.value=ACCOUNT;
  login.elements.password.value='qa031-parent-password';login.requestSubmit();await until(()=>!inFlight&&!!state.data);
  state.route='history';render();window.__testResult={passed:nativeContext!==oldContext&&state.data.user.name.startsWith('Foreign ')
    &&!state.report&&!document.body.textContent.includes('CROSS-VAULT-PRIVATE'),scenario:'different-vault-same-user-ids'};
}catch(error){window.__testResult={passed:false,error:error.stack};}})();
""".replace("ACCOUNT", json.dumps(owner)).replace("ARCHIVE", json.dumps(name))
    cross_result = run_case(cross, cross_script, executable=executable)
    archive = output / "historical"
    archive.mkdir()
    service = Service(archive / "app-data")
    parent = service.register("Historical parent", PASSWORD, "PARENT")
    child = service.register("Historical child", CHILD_PASSWORD, "STUDENT", PROFILE)
    with service.store.transaction():
        service.store.put("session", "empty", {"id": "empty", "subject": "math", "topic": "unknown",
            "created": "2020-01-01", "status": "complete", "messages": [], "task": "", "total": 0,
            "correct": 0, "seconds": 0}, child["id"])
        service.store.put("knowledge", "physics-past", {"subject": "physics", "topic": "retired-physics",
            "attempts_count": 2, "correct_count": 1, "mastery_score": 50, "confidence": .5}, child["id"])
    before = service.store.get("knowledge", "physics-past")
    service.logout()
    script = """
(async()=>{try{
  await rpc('login',{account:ACCOUNT,password:PASSWORD});await refresh();
  const s=student();const checks=[];
  checks.push({id:'QA-002-no-empty-archive',passed:Object.keys(s.archives.history).length===0});
  checks.push({id:'QA-003-physics-preserved',passed:s.knowledge[0].subject==='physics'&&!s.archives.knowledge.math_archive});
  state.route='history';render();checks.push({id:'QA-002-no-empty-option',passed:!document.querySelector('option[value="math_archive"]')});
  state.route='knowledge';render();
  document.querySelector('#knowledge-subject').value='physics';
  document.querySelector('#knowledge-subject').dispatchEvent(new Event('change',{bubbles:true}));
  checks.push({id:'QA-003-visible-under-physics',passed:document.querySelector('.content').textContent.includes('retired-physics')});
  window.__testResult={passed:checks.every(c=>c.passed),checks};
}catch(error){window.__testResult={passed:false,error:error.stack};}})();
""".replace("ACCOUNT", json.dumps(parent["id"])).replace("PASSWORD", json.dumps(PASSWORD))
    archive_result = run_case(archive, script, executable=executable)
    service.login(parent["id"], PASSWORD)
    unchanged = service.store.get("knowledge", "physics-past") == before
    service.logout()
    summary = {"passed": workflow_result["passed"] and archive_result["passed"] and cross_result["passed"] and unchanged,
               "directory": str(output), "workflow": workflow_result, "historical": archive_result,
               "foreign_restore": cross_result,
               "canonical_record_unchanged": unchanged, "cwd": os.environ.get("WINDIR", "C:/Windows")}
    (output / "result.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
