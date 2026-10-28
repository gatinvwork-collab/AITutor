(async()=>{try{
 const wait=ms=>new Promise(r=>setTimeout(r,ms));
 const until=async f=>{for(let n=0;n<200;n++){if(f())return;await wait(50);}throw Error('timeout');};
 const submit=async(selector,values={})=>{const f=document.querySelector(selector);if(!f)throw Error('missing '+selector);for(const[k,v]of Object.entries(values)){if(f.elements[k].type==='checkbox')f.elements[k].checked=v;else f.elements[k].value=v;}f.requestSubmit();await until(()=>!inFlight);};
 await rpc('register',{name:'Intent QA Parent',password:'intent-qa-parent',role:'PARENT'});
 const c=await rpc('register',{name:'Intent QA Child',password:'intent-qa-child',role:'STUDENT',profile:{region:'Region',city:'City',school:'School',grade:7,address:{mode:'manual'}}});
 await rpc('save_provider',{config:{kind:'ollama',model:'synthetic-only',revision:0,endpoint:window.__qaEndpoint}});
 await rpc('logout');await rpc('login',{account:c.id,password:'intent-qa-child'});await refresh();
 navigate('homework');selectLearningSubject('algebra');await learnRefresh();render();
 const payloads={},metadata={};
 for(const intent of ['check','hint','follow_up']){
   await submit('[data-learning-form="work"]');
   const work=learnData().works.at(-1).work;
   const revisionSelector=`[data-learning-form="work_revision"]:has(input[name="work"][value="${work}"])`;
   await submit(revisionSelector,{value:'3x+5=20\n3x=15\nx=5',confirm:true});
   const checkSelector=`[data-learning-form="work_check"]:has(input[name="work"][value="${work}"])`;
   await submit(checkSelector,{intent,follow_up:'Поясни второй шаг'});
   const job=learnData().jobs.find(j=>j.body.kind==='work_check').id;
   let finished=false;
   for(let n=0;n<200;n++){const j=await rpc('learning',{action:'job',job});if(j.status==='succeeded'){finished=true;break;}if(!['pending','running'].includes(j.status))throw Error(JSON.stringify(j));await wait(50);}
   if(!finished)throw Error('job timeout');await learnRefresh();render();
   const call=learnData().calls.find(x=>x.work===work).body;
   payloads[intent]=call.messages;metadata[intent]=call.intent;
   await refresh();const active=student().sessions.find(s=>s.status==='active');if(active)await rpc('pause',{session:active.id});
 }
 window.__testResult={passed:true,meaning:'Reproduction completed; identical=true demonstrates lost intent',version:state.status.version,metadata,
   check_equals_hint:JSON.stringify(payloads.check)===JSON.stringify(payloads.hint),hint_equals_follow_up:JSON.stringify(payloads.hint)===JSON.stringify(payloads.follow_up),payloads};
}catch(error){window.__testResult={passed:false,error:error.stack};}})();
