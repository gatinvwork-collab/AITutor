"""Local CDP transport for the existing exe tests; Qt replaces unavailable Node."""
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtNetwork import QAbstractSocket
from PySide6.QtWebSockets import QWebSocket

port,script_path,result_path,*rest=sys.argv[1:]
endpoint=rest[0] if rest else ""
app=QCoreApplication([])
ws=QWebSocket()
messages={}
sequence=0
def receive(raw):
    value=json.loads(raw)
    if "id" in value:
        messages[value["id"]]=value
ws.textMessageReceived.connect(receive)
def spin(condition,seconds):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        app.processEvents()
        if condition():
            return True
        time.sleep(.01)
    return False
target=None
deadline=time.monotonic()+90
while time.monotonic()<deadline:
    try:
        with urllib.request.urlopen("http://127.0.0.1:"+port+"/json/list",timeout=1) as response:
            targets=json.load(response)
        target=next((t for t in targets if t.get("type")=="page" and "index.html" in t.get("url","")),None)
    except Exception:
        pass
    if target:
        break
    time.sleep(.2)
assert target, "Application CDP target not available"
ws.open(QUrl(target["webSocketDebuggerUrl"]))
assert spin(lambda:ws.state()==QAbstractSocket.SocketState.ConnectedState,15),ws.errorString()
def call(method,params=None):
    global sequence
    sequence+=1
    current=sequence
    ws.sendTextMessage(json.dumps({"id":current,"method":method,"params":params or {}}))
    assert spin(lambda:current in messages,20),"CDP timeout: "+method
    value=messages.pop(current)
    if value.get("error"):
        raise RuntimeError(value["error"])
    return value.get("result",{})
def evaluate(expression):
    value=call("Runtime.evaluate",{"expression":expression,"returnByValue":True})
    if value.get("exceptionDetails"):
        raise RuntimeError(value["exceptionDetails"])
    return value.get("result",{}).get("value")
assert spin(lambda:evaluate("typeof bridge!=='undefined'&&!!bridge&&!inFlight"),40),"Bridge not ready"
evaluate("window.__qaEndpoint="+json.dumps(endpoint))
evaluate(Path(script_path).read_text(encoding="utf-8"))
result=None
deadline=time.monotonic()+100
while time.monotonic()<deadline:
    result=evaluate("window.__testResult||null")
    if result:
        break
    spin(lambda:False,.1)
result=result or {"passed":False,"error":"QA timeout"}
Path(result_path).write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
shot=call("Page.captureScreenshot",{"format":"png"})
Path(result_path).with_suffix(".png").write_bytes(base64.b64decode(shot["data"]))
call("Runtime.evaluate",{"expression":"rpc('logout')","awaitPromise":True,"returnByValue":True})
ws.close()
print(json.dumps(result,ensure_ascii=False))
raise SystemExit(0 if result["passed"] else 1)
