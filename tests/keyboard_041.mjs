// Trusted Chromium keyboard events against the actual compiled WebView.
import fs from 'node:fs';
const [port,metadataFile,out]=process.argv.slice(2);
const fixture=JSON.parse(fs.readFileSync(metadataFile,'utf8')).fixtures[0];
const pause=ms=>new Promise(r=>setTimeout(r,ms));let target;
for(let n=0;n<450;n++){try{target=(await(await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(t=>t.type==='page'&&t.url.includes('index.html'));}catch{}if(target)break;await pause(200);}
if(!target)throw Error('No application page');
const ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise(r=>ws.addEventListener('open',r,{once:true}));
let sequence=0;const jobs=new Map();
ws.addEventListener('message',event=>{const value=JSON.parse(String(event.data));const job=jobs.get(value.id);if(job){jobs.delete(value.id);value.error?job.reject(Error(value.error.message)):job.resolve(value.result);}});
const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;jobs.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
async function evaluate(expression,awaitPromise=false){const result=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;}
for(let n=0;n<300;n++){if(await evaluate("typeof bridge!=='undefined'&&!!bridge&&!inFlight"))break;await pause(100);}
await call('Emulation.setFocusEmulationEnabled',{enabled:true});
const checks=[];
for(const role of ['PARENT','STUDENT']){
 await evaluate(`(async()=>{if(state.data)await rpc('logout');await rpc('login',{account:${JSON.stringify(role==='PARENT'?fixture.parent:fixture.child)},password:'qa-feedback-password'});await refresh();})()`,true);
 for(const design of ['strict','modern'])for(const theme of ['light','dark','system']){
  await evaluate(`(async()=>{await rpc('set_theme',{theme:${JSON.stringify(theme)},design:${JSON.stringify(design)}});await refresh();})()`,true);
  const routes=await evaluate(role==='PARENT'?'parentNav.map(x=>x[0])':'studentNav.map(x=>x[0])');
  for(const route of routes)for(const key of ['Enter',' ']){
   await evaluate(`window.__navButton=document.querySelector('nav [data-value="${route}"]');window.__navButton.focus();`);
   await call('Input.dispatchKeyEvent',{type:'keyDown',key,code:key==='Enter'?'Enter':'Space',windowsVirtualKeyCode:key==='Enter'?13:32,text:key==='Enter'?'\r':' ',unmodifiedText:key==='Enter'?'\r':' '});
   await call('Input.dispatchKeyEvent',{type:'keyUp',key,code:key==='Enter'?'Enter':'Space',windowsVirtualKeyCode:key==='Enter'?13:32});
   await pause(25);
   const state=await evaluate(`({route:state.route,active:document.querySelector('nav [aria-current="page"]')?.dataset.value,focused:document.activeElement===window.__navButton,connected:window.__navButton.isConnected})`);
   checks.push({role,design,theme,route,key,passed:state.route===route&&state.active===route&&state.focused&&state.connected});
   await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
   await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
   checks.push({role,design,theme,route,key:'Tab',passed:await evaluate("document.activeElement.tagName==='BUTTON'&&document.activeElement!==window.__navButton")});
  }
 }
}
const result={passed:checks.every(x=>x.passed),checks};
fs.writeFileSync(out,JSON.stringify(result,null,2));
await evaluate("rpc('logout')",true);ws.close();
console.log(JSON.stringify({passed:result.passed,checks:checks.length,failed:checks.filter(x=>!x.passed).length}));
if(!result.passed)process.exitCode=1;
