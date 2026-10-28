(async()=>{const checks=[];try{
 const check=(name,ok)=>{checks.push({name,ok:!!ok});if(!ok)throw Error(name);};
 const wait=ms=>new Promise(r=>setTimeout(r,ms));
 const until=async f=>{for(let n=0;n<250;n++){if(f())return;await wait(40);}throw Error('timeout');};
 const submit=async(selector,values={},flip=false)=>{const f=document.querySelector(selector);if(!f)throw Error('missing '+selector);
   for(const[k,v]of Object.entries(values)){if(f.elements[k].type==='checkbox')f.elements[k].checked=v;else f.elements[k].value=v;}
   f.requestSubmit();if(flip)f.elements.intent.value=values.intent==='hint'?'check':'hint';await until(()=>!inFlight);};
 const c=await rpc('register',{name:'Intent Parent',password:'intent-parent-052',role:'PARENT'});
 const child=await rpc('register',{name:'Intent Child',password:'intent-child-052',role:'STUDENT',profile:{region:'Region',city:'City',school:'School',grade:7,address:{mode:'manual'}}});
 await rpc('save_provider',{config:{kind:'ollama',model:'synthetic',revision:0,endpoint:window.__qaEndpoint}});
 await rpc('logout');await rpc('login',{account:child.id,password:'intent-child-052'});await refresh();
 navigate('homework');selectLearningSubject('algebra');await learnRefresh();render();
 const instructions={check:'Проверь решение.',hint:'Дай подсказку.',follow_up:'Продолжи разбор решения.'};
 const payloads=[];
 for(const intent of ['check','hint','follow_up'])for(const question of ['','   ','Поясни второй шаг']){
   await submit('[data-learning-form="work"]');const work=learnData().works.at(-1).work;
   await submit(`[data-learning-form="work_revision"]:has(input[name="work"][value="${work}"])`,{value:'3x+5=20\n3x=15\nx=5',confirm:true});
   await submit(`[data-learning-form="work_check"]:has(input[name="work"][value="${work}"])`,{intent,follow_up:question},true);
   const job=learnData().jobs.find(j=>j.body.kind==='work_check').id;
   for(let n=0;n<250;n++){const j=await rpc('learning',{action:'job',job});if(j.status==='succeeded')break;if(!['pending','running'].includes(j.status))throw Error(JSON.stringify(j));await wait(40);}
   await learnRefresh();render();const body=learnData().calls.find(x=>x.work===work).body;
   const label=intent+'/'+JSON.stringify(question);
   check(label+' selected intent snapshot',body.intent===intent);
   check(label+' semantic control',body.messages[0].content.includes(`Текущее действие (intent): ${intent}. ${instructions[intent]}`));
   check(label+' clarification additive',body.messages.at(-1).content===(question.trim()||instructions[intent]));
   payloads.push({intent,question,messages:body.messages});
   await refresh();const active=student().sessions.find(s=>s.status==='active');if(active)await rpc('pause',{session:active.id});
 }
 // Different modes in one work: past mode is provenance, current mode stays authoritative.
 const work=learnData().works.at(-1).work;
 for(const intent of ['hint','check','follow_up']){
   await submit(`[data-learning-form="work_check"]:has(input[name="work"][value="${work}"])`,{intent,follow_up:'NEXT '+intent});
   const job=learnData().jobs.find(j=>j.body.kind==='work_check').id;
   for(let n=0;n<250;n++){const j=await rpc('learning',{action:'job',job});if(j.status==='succeeded')break;if(!['pending','running'].includes(j.status))throw Error(JSON.stringify(j));await wait(40);}
   await learnRefresh();render();const body=learnData().calls.filter(x=>x.work===work).at(-1).body;
   check('consecutive current '+intent,body.messages[0].content.includes(`Текущее действие (intent): ${intent}. ${instructions[intent]}`));
   check('consecutive pairs '+intent,body.messages.filter(m=>m.role==='assistant').length===['hint','check','follow_up'].indexOf(intent)+1);
   payloads.push({intent,question:'NEXT '+intent,messages:body.messages});
 }
 window.__testResult={passed:true,checks,payloads,version:state.status.version};
}catch(error){window.__testResult={passed:false,error:error.stack,checks};}})();
