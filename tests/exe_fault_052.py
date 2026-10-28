"""Real Windows replacement denial on an isolated a2 -> a3 Portable copy.

No disk filling or product fault switches. Hold a read handle without
FILE_SHARE_DELETE; release it in finally even if the UI test fails.
"""

import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import threading
import uuid

from tests.exe_qa_031 import ROOT, free_port, close_test_process
from tests.upgrade_051 import CHILD_PASSWORD
from tutor_ai import __version__


def main():
    folder = ROOT / "build" / ("exe-fault052-" + uuid.uuid4().hex[:8])
    folder.mkdir()
    source = ROOT / "build/qa052-a2-source"
    expected = json.loads((source / "expected.json").read_text(encoding="utf-8"))
    shutil.copytree(source / "app-data", folder / "app-data")
    source_hash = hashlib.sha256((source / "app-data/data/vault.aead").read_bytes()).hexdigest()
    executable = ROOT / "dist" / f"Tutor-AI-{__version__}.exe"
    exe = folder / executable.name
    os.link(executable, exe)
    script = r"""(async()=>{const checks=[];try{
      const check=(name,ok)=>{checks.push({name,ok:!!ok});if(!ok)throw Error(name);};
      const wait=ms=>new Promise(r=>setTimeout(r,ms));
      const lc=(action,args={})=>rpc('learning',{action,...args});
      const phase=async name=>{window.__faultStage=name;for(let i=0;i<150;i++){
        if(window.__faultAck===name)return;await wait(100);}throw Error('fault handshake '+name);};
      await rpc('login',{account:CHILD,password:PASS});await refresh();
      let row=await lc('attempt',{attempt:ATTEMPT});
      check('crash requires explicit resume',row.status==='paused');
      await lc('resume',{attempt:ATTEMPT,expected_revision:row.revision,operation_id:'fault-resume'});
      const before=await lc('attempt',{attempt:ATTEMPT});
      const dailyBefore=(await rpc('snapshot')).students[0].daily.seconds;
      await phase('lock');
      await wait(186000); // Real monotonic idle boundary, no product clock injection.
      row=await lc('attempt',{attempt:ATTEMPT});
      check('failed autopause remains persisted active',row.status==='active');
      check('failed checkpoints do not publish seconds',row.body.seconds===before.body.seconds);
      check('failed checkpoints do not publish daily',(await rpc('snapshot')).students[0].daily.seconds===dailyBefore);
      check('background failure is visible',!document.querySelector('#checkpoint-warning').hidden);
      let refused=false;try{await lc('pause',{attempt:ATTEMPT,expected_revision:row.revision,operation_id:'fault-pause'});}catch(e){refused=e.message.includes('записать');}
      check('unsaved pause does not report success',refused);
      await phase('unlock');
      for(let i=0;i<100;i++){row=await lc('attempt',{attempt:ATTEMPT});if(row.status==='paused')break;await wait(100);}
      check('retry completes autopause',row.status==='paused');
      check('retry bills exactly allowed idle',Math.abs(row.body.seconds-before.body.seconds-180)<0.000001);
      const dailyAfter=(await rpc('snapshot')).students[0].daily.seconds;
      check('daily agrees with attempt',Math.abs(dailyAfter-dailyBefore-180)<0.000001);
      check('warning clears after successful checkpoint',document.querySelector('#checkpoint-warning').hidden);
      await wait(6000);
      const again=await lc('attempt',{attempt:ATTEMPT});
      check('later ticks do not duplicate time',again.body.seconds===row.body.seconds);
      window.__testResult={passed:true,checks,before:before.body.seconds,after:row.body.seconds,dailyBefore,dailyAfter};
    }catch(e){window.__testResult={passed:false,checks,error:e.stack};}})();"""
    for key, value in [("CHILD", expected["child"]), ("PASS", CHILD_PASSWORD), ("ATTEMPT", expected["attempt"])]:
        script = script.replace(key, json.dumps(value))
    (folder / "case.js").write_text(script, encoding="utf-8")
    runner = (ROOT / "tests/exe_cdp_runner.mjs").read_text(encoding="utf-8")
    runner = runner.replace("n<900", "n<2500")
    runner = runner.replace("result=await evaluate('window.__testResult||null');", """
      const stage=await evaluate('window.__faultStage||null');
      if(stage){const base=resultFile.replace(/result.json$/,'');
        fs.writeFileSync(base+'stage.txt',stage);
        if(fs.existsSync(base+stage+'.ack'))await evaluate('window.__faultAck='+JSON.stringify(stage));}
      result=await evaluate('window.__testResult||null');""")
    (folder / "runner.mjs").write_text(runner, encoding="utf-8")
    stop = threading.Event()
    faults = {}

    def controller():
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong,
                                       ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = None
        vault = folder / "app-data/data/vault.aead"
        try:
            while not stop.wait(0.1):
                request = folder / "stage.txt"
                stage = request.read_text() if request.exists() else ""
                if stage == "lock" and not handle:
                    faults["locked_hash"] = hashlib.sha256(vault.read_bytes()).hexdigest()
                    handle = kernel.CreateFileW(str(vault), 0x80000000, 3, None, 3, 0x80, None)
                    if handle == ctypes.c_void_p(-1).value:
                        handle = None
                        raise ctypes.WinError(ctypes.get_last_error())
                    (folder / "lock.ack").write_text("ok")
                if stage == "unlock" and handle:
                    faults["vault_unchanged_during_denial"] = faults["locked_hash"] == hashlib.sha256(vault.read_bytes()).hexdigest()
                    kernel.CloseHandle(handle)
                    handle = None
                    (folder / "unlock.ack").write_text("ok")
                    return
        except Exception as exc:
            faults["error"] = type(exc).__name__
        finally:
            if handle:
                kernel.CloseHandle(handle)

    thread = threading.Thread(target=controller, daemon=True)
    thread.start()
    port = free_port()
    env = {**os.environ, "QTWEBENGINE_REMOTE_DEBUGGING": f"127.0.0.1:{port}"}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    with (folder / "process.log").open("wb") as log:
        process = subprocess.Popen([str(exe)], cwd=os.environ.get("WINDIR", "C:/Windows"), env=env,
                                   stdout=log, stderr=log, startupinfo=startup)
        try:
            completed = subprocess.run(["node", str(folder / "runner.mjs"), str(port),
                                        str(folder / "case.js"), str(folder / "result.json")],
                                       capture_output=True, timeout=300)
            (folder / "runner.log").write_bytes(completed.stdout + completed.stderr)
        finally:
            stop.set()
            thread.join(timeout=5)
            close_test_process(process, exe)
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    result.update(faults=faults, sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                  source_a2_unchanged=source_hash == hashlib.sha256((source / "app-data/data/vault.aead").read_bytes()).hexdigest())
    result["passed"] = result["passed"] and faults.get("vault_unchanged_during_denial", False) and result["source_a2_unchanged"]
    (folder / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"directory": str(folder), **result}))
    return 0 if completed.returncode == 0 and result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
