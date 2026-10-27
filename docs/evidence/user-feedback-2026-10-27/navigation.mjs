// Measure real pointer events in a frozen Qt WebView. No external services.
import fs from 'node:fs';
import path from 'node:path';
const [port, fixtureFile, label, outputFile] = process.argv.slice(2);
const isolated=process.argv[6]==='isolated';
const fixture=JSON.parse(fs.readFileSync(fixtureFile,'utf8')).fixtures.find(f=>f.label===label);
const pause=ms=>new Promise(r=>setTimeout(r,ms));
let target;
for(let n=0;n<400;n++){
  try{target=(await(await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(t=>t.type==='page'&&t.url.includes('index.html'));}catch{}
  if(target)break;await pause(200);
}
if(!target)throw Error('Application target not found');
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
let sequence=0;const jobs=new Map();
ws.addEventListener('message',event=>{const v=JSON.parse(String(event.data));const j=jobs.get(v.id);if(j){jobs.delete(v.id);clearTimeout(j.timer);v.error?j.reject(Error(v.error.message)):j.resolve(v.result);}});
function call(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence;const timer=setTimeout(()=>{jobs.delete(id);reject(Error('CDP timeout '+method));},65000);jobs.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression,awaitPromise=false){const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
for(let n=0;n<300;n++){if(await evaluate("typeof bridge!=='undefined'&&!!bridge&&!inFlight"))break;await pause(100);}
const loginMs=performance.now();
await evaluate(`(async()=>{await rpc('login',{account:${JSON.stringify(fixture.parent)},password:'qa-feedback-password'});await refresh();return true;})()`,true);
const result={fixture:label,parent_login_ms:performance.now()-loginMs,clicks:[],keyboard:[],rpc:[],errors:[]};
result.viewport=await evaluate('({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,screenWidth:screen.width,screenHeight:screen.height,userAgent:navigator.userAgent})');
await evaluate(`(()=>{
window.__qaClick=null;window.__qaRender=[];window.__qaErrors=[];
const base=render;render=function(){const start=performance.now();try{return base();}finally{window.__qaRender.push(performance.now()-start);}};
addEventListener('error',e=>window.__qaErrors.push(e.message));
document.addEventListener('click',e=>{const b=e.target.closest('nav button[data-action="route"]');if(!b)return;
  const m={requested:b.dataset.value,trusted:e.isTrusted,started:performance.now(),before:state.route};window.__qaClick=m;
  requestAnimationFrame(()=>requestAnimationFrame(()=>Object.assign(m,{ready:true,elapsed_ms:performance.now()-m.started,
    route:state.route,active:document.querySelector('nav button.active')?.dataset.value,
    heading:document.querySelector('.content h1')?.textContent,render_ms:window.__qaRender.at(-1),
    focus:document.activeElement?.tagName,inFlight})));
},true);
return true;})()`);
async function click(route,position='center'){
  const rect=await evaluate(`(()=>{const b=document.querySelector('nav button[data-value="${route}"]');if(!b)throw Error('Missing route ${route}');b.scrollIntoView({block:'nearest',behavior:'instant'});const r=b.getBoundingClientRect();window.__qaClick=null;return {x:r.x+(${JSON.stringify(position)}==='left'?4:${JSON.stringify(position)}==='right'?r.width-4:r.width/2),y:r.y+r.height/2,disabled:b.disabled};})()`);
  const start=performance.now();
  await call('Input.dispatchMouseEvent',{type:'mouseMoved',x:rect.x,y:rect.y});
  await call('Input.dispatchMouseEvent',{type:'mousePressed',x:rect.x,y:rect.y,button:'left',clickCount:1});
  await call('Input.dispatchMouseEvent',{type:'mouseReleased',x:rect.x,y:rect.y,button:'left',clickCount:1});
  let item;
  for(let n=0;n<650;n++){item=await evaluate('window.__qaClick');if(item?.ready)break;await pause(100);}
  item={...item,requested:route,position,driver_elapsed_ms:performance.now()-start,button_disabled:rect.disabled};
  item.correct=!!item.ready&&item.route===route&&item.active===route;
  return item;
}
try{
  if(isolated){
    for(const design of ['strict','modern'])for(const route of ['notifications','home','students']){
      await evaluate(`(async()=>{await rpc('logout');await rpc('login',{account:${JSON.stringify(fixture.parent)},password:'qa-feedback-password'});await rpc('set_theme',{theme:'light',design:'${design}'});await refresh();return true;})()`,true);
      result.clicks.push({...await click(route),design,role:'PARENT',isolated:true});
    }
  }else{
  for(const design of ['strict','modern']){
    await evaluate(`(async()=>{await rpc('set_theme',{theme:'light',design:'${design}'});await refresh();return true;})()`,true);
    for(let n=0;n<100;n++)for(const route of ['notifications','home','students']){
      const item=await click(route);result.clicks.push({...item,design,iteration:n,role:'PARENT'});
    }
    const routes=await evaluate('parentNav.map(x=>x[0])');
    for(const route of routes)for(const position of ['left','right'])result.clicks.push({...await click(route,position),design,role:'PARENT',matrix:true});
    await evaluate(`(()=>{state.route='home';render();document.querySelector('nav button[data-value="home"]').focus();return true;})()`);
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
    const focused=await evaluate('document.activeElement?.dataset?.value');
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    await pause(80);
    result.keyboard.push({design,focused_before_enter:focused,...await evaluate('({route:state.route,focus_after_enter:document.activeElement?.tagName,active:document.querySelector("nav button.active")?.dataset.value})')});
  }
  }
  for(let n=0;n<5;n++){
    const t=performance.now();await evaluate("rpc('status')",true);result.rpc.push({command:'status',ms:performance.now()-t});
    const q=performance.now();await evaluate("rpc('snapshot')",true);result.rpc.push({command:'snapshot',ms:performance.now()-q});
  }
  await call('Page.captureScreenshot',{format:'png'}).then(r=>fs.writeFileSync(outputFile.replace(/\.json$/,'.png'),Buffer.from(r.data,'base64')));
  await evaluate(`(async()=>{await rpc('logout');await rpc('login',{account:${JSON.stringify(fixture.child)},password:'qa-feedback-password'});await refresh();return true;})()`,true);
  if(!isolated)for(const route of await evaluate('studentNav.map(x=>x[0])'))for(const position of ['center','left','right'])result.clicks.push({...await click(route,position),design:'modern',role:'STUDENT',matrix:true});
  result.errors=await evaluate('window.__qaErrors');
  result.passed=result.clicks.every(x=>x.correct)&&result.errors.length===0;
}catch(error){result.passed=false;result.error=error.stack;}
fs.writeFileSync(outputFile,JSON.stringify(result,null,2));
await evaluate("rpc('logout')",true);ws.close();
console.log(JSON.stringify({fixture:label,passed:result.passed,clicks:result.clicks.length,wrong:result.clicks.filter(x=>!x.correct).length,error:result.error}));
if(!result.passed)process.exitCode=1;
