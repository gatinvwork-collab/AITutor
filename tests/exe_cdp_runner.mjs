// Local developer-test runner, never loaded by the application.
import fs from 'node:fs';
const [port,scriptFile,resultFile,endpoint='']=process.argv.slice(2);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let target;
for(let n=0;n<450;n++){
  try{target=(await(await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(t=>t.type==='page'&&t.url.includes('index.html'));}catch{}
  if(target)break;await sleep(200);
}
if(!target)throw Error('No application target');
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
let sequence=0;const jobs=new Map();
ws.addEventListener('message',event=>{const value=JSON.parse(String(event.data));const job=jobs.get(value.id);if(job){jobs.delete(value.id);clearTimeout(job.timer);value.error?job.reject(Error(value.error.message)):job.resolve(value.result);}});
function call(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence;const timer=setTimeout(()=>{jobs.delete(id);reject(Error('CDP timeout: '+method));},15000);jobs.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const result=await call('Runtime.evaluate',{expression,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;}
let ready=false;
for(let n=0;n<300;n++){ready=await evaluate("typeof bridge!=='undefined'&&!!bridge&&!inFlight");if(ready)break;await sleep(100);}
if(!ready)throw Error('Bridge not ready');
await evaluate('window.__qaEndpoint='+JSON.stringify(endpoint));
await evaluate(fs.readFileSync(scriptFile,'utf8'));
let result;
for(let n=0;n<900;n++){result=await evaluate('window.__testResult||null');if(result)break;await sleep(100);}
result??={passed:false,error:'Test timeout'};
fs.writeFileSync(resultFile,JSON.stringify(result,null,2));
const shot=await call('Page.captureScreenshot',{format:'png'});
fs.writeFileSync(resultFile.replace(/\.json$/,'.png'),Buffer.from(shot.data,'base64'));
await call('Runtime.evaluate',{expression:"rpc('logout')",awaitPromise:true,returnByValue:true});
ws.close();
console.log(JSON.stringify(result));
if(!result.passed)process.exitCode=1;
