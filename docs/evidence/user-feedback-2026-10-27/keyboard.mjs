import fs from 'node:fs';
const [port,metadataFile,out]=process.argv.slice(2);
const fixture=JSON.parse(fs.readFileSync(metadataFile,'utf8')).fixtures[0];
const pause=ms=>new Promise(r=>setTimeout(r,ms));let target;
for(let n=0;n<400;n++){try{target=(await(await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(t=>t.type==='page'&&t.url.includes('index.html'));}catch{}if(target)break;await pause(200);}
if(!target)throw Error('No target');
const ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise(resolve=>ws.addEventListener('open',resolve,{once:true}));
let sequence=0;const jobs=new Map();
ws.addEventListener('message',event=>{const v=JSON.parse(String(event.data));const j=jobs.get(v.id);if(j){jobs.delete(v.id);v.error?j.reject(Error(v.error.message)):j.resolve(v.result);}});
const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;jobs.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
async function evaluate(expression,awaitPromise=false){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
for(let n=0;n<300;n++){if(await evaluate("typeof bridge!=='undefined'&&!!bridge&&!inFlight"))break;await pause(100);}
await call('Emulation.setFocusEmulationEnabled',{enabled:true});
await evaluate(`(async()=>{await rpc('login',{account:'${fixture.parent}',password:'qa-feedback-password'});await refresh();return true;})()`,true);
const result=[];
for(const design of ['strict','modern'])for(const key of ['Enter',' ']){
  await evaluate(`(async()=>{await rpc('set_theme',{theme:'light',design:'${design}'});await refresh();state.route='home';render();document.querySelector('nav button[data-value="students"]').focus();return true;})()`,true);
  const before=await evaluate('({route:state.route,focused:document.activeElement?.dataset?.value,hasFocus:document.hasFocus()})');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key,code:key==='Enter'?'Enter':'Space',windowsVirtualKeyCode:key==='Enter'?13:32,text:key==='Enter'?'\r':' ',unmodifiedText:key==='Enter'?'\r':' '});
  await call('Input.dispatchKeyEvent',{type:'keyUp',key,code:key==='Enter'?'Enter':'Space',windowsVirtualKeyCode:key==='Enter'?13:32});await pause(100);
  const after=await evaluate('({route:state.route,focused:document.activeElement?.dataset?.value,tag:document.activeElement?.tagName,hasFocus:document.hasFocus(),active:document.querySelector("nav button.active")?.dataset.value})');
  result.push({design,key,before,after});
}
fs.writeFileSync(out,JSON.stringify(result,null,2));
const shot=await call('Page.captureScreenshot',{format:'png'});fs.writeFileSync(out.replace(/\.json$/,'.png'),Buffer.from(shot.data,'base64'));
await evaluate("rpc('logout')",true);ws.close();console.log(JSON.stringify(result));
