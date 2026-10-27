// Passive observation after test-fixture login; actual inputs use Computer Use.
import fs from 'node:fs';
const [port,metaFile,out]=process.argv.slice(2);
const fixture=JSON.parse(fs.readFileSync(metaFile,'utf8')).fixtures[0];
const pause=ms=>new Promise(r=>setTimeout(r,ms));let target;
for(let n=0;n<400;n++){try{target=(await(await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(t=>t.type==='page'&&t.url.includes('index.html'));}catch{}if(target)break;await pause(200);}
if(!target)throw Error('No target');
const ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise(resolve=>ws.addEventListener('open',resolve,{once:true}));
let sequence=0;const jobs=new Map();let stopped=false;
ws.addEventListener('message',event=>{const v=JSON.parse(String(event.data));const j=jobs.get(v.id);if(j){jobs.delete(v.id);v.error?j.reject(Error(v.error.message)):j.resolve(v.result);}});
ws.addEventListener('close',()=>{stopped=true;});
const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;jobs.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
async function evaluate(expression,awaitPromise=false){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
for(let n=0;n<300;n++){if(await evaluate("typeof bridge!=='undefined'&&!!bridge&&!inFlight"))break;await pause(100);}
await evaluate(`(async()=>{await rpc('login',{account:'${fixture.parent}',password:'qa-feedback-password'});await refresh();window.__qaNativeClicks=[];document.addEventListener('click',e=>{const b=e.target.closest('nav button');if(!b)return;const r={requested:b.dataset.value,trusted:e.isTrusted,at:performance.now()};window.__qaNativeClicks.push(r);requestAnimationFrame(()=>requestAnimationFrame(()=>Object.assign(r,{route:state.route,heading:document.querySelector('.content h1')?.textContent,elapsed_ms:performance.now()-r.at})));},true);return true;})()`,true);
console.log('READY');
while(!stopped){
  try{const value=await evaluate('({route:state.route,clicks:window.__qaNativeClicks,viewport:{width:innerWidth,height:innerHeight,dpr:devicePixelRatio}})');fs.writeFileSync(out,JSON.stringify(value,null,2));}catch{break;}
  await pause(500);
}
process.exit(0);
