"""a2 acceptance: assertions over original independent witnesses, plus UI subjects."""

import hashlib
import json
import shutil
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tests.exe_qa_031 import ROOT, run_case
from tests.gui_learning_050 import DemoProvider
from tutor_ai import __version__


def main(version=__version__):
    executable = ROOT / "dist" / f"Tutor-AI-{version}.exe"
    output = ROOT / "build" / ("exe-qa051-" + uuid.uuid4().hex[:8])
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
    threading.Thread(target=server.serve_forever, daemon=True).start()
    endpoint = f"http://127.0.0.1:{server.server_port}"
    try:
        edges = output / "edges"
        edges.mkdir()
        script = (ROOT / "docs/evidence/qa-independent-050-2026-10-28/compiled_edges.js").read_text(
            encoding="utf-8"
        )
        # The original reproduction reports success even for product failures.
        # Keep its steps, but assert its actual witnesses before accepting.
        script = script.replace(
            "window.__testResult={passed:true,meaning:",
            "if(chosen!=='informatics'||createdSubject!=='informatics'||!dialogue.previous_user_turn_in_second_request||b.status!=='active'||b.body.seconds<=before)throw Error('QA-050 regression');window.__testResult={passed:true,meaning:",
        )
        script=script.replace("const before=(await lc('attempt',{attempt:bid})).body.seconds;",
            "const dailyBefore=(await rpc('snapshot')).students.find(s=>s.id===child.id).daily.seconds;const before=(await lc('attempt',{attempt:bid})).body.seconds;")
        script=script.replace("window.__testResult={passed:true,meaning:",
            "const dailyAfter=(await rpc('snapshot')).students.find(s=>s.id===child.id).daily.seconds;if(dailyAfter<=dailyBefore)throw Error('daily counter did not advance');window.__testResult={passed:true,meaning:")
        script=script.replace("timer:{status:b.status,before,after:b.body.seconds,advanced:",
            "timer:{status:b.status,before,after:b.body.seconds,dailyBefore,dailyAfter,advanced:")
        observed = run_case(edges, script, endpoint, executable, prefer_link=True)
        subjects = output / "subjects"
        subjects.mkdir()
        subject_result = run_case(
            subjects,
            (ROOT / "tests/gui_qa_051.js").read_text(encoding="utf-8"),
            endpoint,
            executable,
            prefer_link=True,
        )
        source = ROOT / "build/qa051-a1-source-final"
        before = hashlib.sha256((source / "app-data/data/vault.aead").read_bytes()).hexdigest()
        upgrade = output / "a1-upgrade"
        upgrade.mkdir()
        shutil.copytree(source / "app-data", upgrade / "app-data")
        expected = json.loads((source / "expected.json").read_text(encoding="utf-8"))
        upgrade_script = """(async()=>{const checks=[];try{const check=(name,ok)=>{checks.push({name,ok:!!ok});if(!ok)throw Error(name);};
        await rpc('login',{account:PARENT,password:PASSWORD});await refresh();
        check('a2 version',state.status.version==='0.5.0a2');check('family',state.data.students.length===1);
        navigate('learning');await learnRefresh();render();
        check('prior collection retained',learnData().collections.length===1);check('prior work retained',learnData().works.some(w=>w.work===WORK));
        check('prior payload retains first question',learnData().calls.some(c=>JSON.stringify(c.body.messages).includes('OLD051 FIRST')));
        // Only this isolated test copy is reconfigured to a loopback model.
        await rpc('save_provider',{config:{kind:'ollama',model:'synthetic',endpoint:window.__qaEndpoint,revision:state.data.provider.revision}});
        await rpc('logout');await rpc('login',{account:CHILD,password:CHILDPASS});await refresh();navigate('learning');await learnRefresh();render();
        check('crashed attempt paused',learnData().attempts.every(a=>a.status!=='active'));
        const call=await learnCall('work_check',{work:WORK,expected_revision:2,intent:'follow_up',follow_up:'NEW EXE QUESTION'});
        for(let i=0;i<200;i++){const job=await rpc('learning',{action:'job',job:call.job});if(job.status==='succeeded')break;if(job.status==='failed'||job.status==='stale')throw Error(JSON.stringify(job));await new Promise(r=>setTimeout(r,40));}
        await learnRefresh();render();const messages=learnData().calls.filter(c=>c.work===WORK).at(-1).body.messages;
        check('old clarification used prospectively',JSON.stringify(messages).includes('OLD051 FIRST'));
        check('old subject unchanged',learnData().works.filter(w=>w.work===WORK).every(w=>w.body.subject==='algebra'));
        window.__testResult={passed:true,checks};}catch(error){window.__testResult={passed:false,error:error.stack,checks};}})();"""
        from tests.upgrade_051 import PASSWORD, CHILD_PASSWORD

        upgrade_script = upgrade_script.replace("==='0.5.0a2'", "===" + json.dumps(version))
        for marker, value in [
            ("PARENT", expected["parent"]),
            ("PASSWORD", PASSWORD),
            ("CHILDPASS", CHILD_PASSWORD),
            ("CHILD", expected["child"]),
            ("WORK", expected["work"]),
        ]:
            upgrade_script = upgrade_script.replace(marker, json.dumps(value))
        upgraded = run_case(upgrade, upgrade_script, endpoint, executable, prefer_link=True)
        result = {
            "passed": observed["passed"] and subject_result["passed"] and upgraded["passed"],
            "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "edges": observed,
            "subjects": subject_result,
            "upgrade_a1": upgraded,
            "source_a1_unchanged": before
            == hashlib.sha256((source / "app-data/data/vault.aead").read_bytes()).hexdigest(),
        }
        result["passed"] = result["passed"] and result["source_a1_unchanged"]
        (output / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"directory": str(output), **result}))
        return 0 if result["passed"] else 1
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
