"""Verify the native timer boundary on the actual exe, local Ollama stub only."""
import json
import subprocess
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from tests.exe_qa_031 import run_case
original_run=subprocess.run
def redirected(args,*positional,**kwargs):
    if isinstance(args,list) and args[0]=="node":
        args=[sys.executable,"-X","utf8",str(OUT/"cdp_qt.py"),*args[2:]]
    return original_run(args,*positional,**kwargs)
subprocess.run=redirected
class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length","0")))
        raw=json.dumps({"message":{"content":"Local QA response"},"eval_count":1}).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def log_message(self,*args):
        pass
server=ThreadingHTTPServer(("127.0.0.1",0),Stub)
threading.Thread(target=server.serve_forever,daemon=True).start()
directory=ROOT/"build"/("qa-retest031-exe-boundary-"+uuid.uuid4().hex[:8])
directory.mkdir()
script=r"""
(async()=>{try{
  const p=await rpc('register',{name:'Timer QA Parent',password:'qa-parent-password',role:'PARENT'});
  const c=await rpc('register',{name:'Timer QA Child',password:'qa-child-password',role:'STUDENT',
    profile:{region:'Region',city:'City',school:'School',grade:7,address:{mode:'manual'}}});
  await rpc('save_provider',{config:{kind:'ollama',model:'local-only',endpoint:window.__qaEndpoint,revision:0}});
  await rpc('logout');await rpc('login',{account:c.id,password:'qa-child-password'});await refresh();
  const older=await rpc('start_lesson',{topic_id:'math-equations'});await rpc('pause',{session:older.id});
  const current=await rpc('start_lesson',{topic_id:'physics-speed'});await refresh();
  const before=student().daily.seconds;
  // The protected native API must preserve the timer of a different active session.
  await rpc('pause',{session:older.id});
  await new Promise(r=>setTimeout(r,6500));
  await refresh();state.lesson=student().sessions.find(s=>s.id===current.id);state.route='lesson';render();
  const after=student().daily.seconds;
  window.__testResult={passed:after-before>=5,scenario:'pause-old-session-while-current-is-active',
    observations:{before,after,delta:after-before,currentStatus:state.lesson.status},
    expected:'active session charges at least 5 seconds during 6.5 seconds wait'};
}catch(error){window.__testResult={passed:false,error:error.stack};}})();
"""
try:
    try:
        run_case(directory,script,"http://127.0.0.1:"+str(server.server_port))
    except RuntimeError:
        if not (directory/"result.json").exists():
            raise
finally:
    server.shutdown()
    server.server_close()
data=json.loads((directory/"result.json").read_text(encoding="utf-8"))
data["directory"]=str(directory)
(OUT/"exe-boundary-result.json").write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
print(json.dumps(data))
