(async()=>{try{
 const wait=ms=>new Promise(r=>setTimeout(r,ms));
 const until=async f=>{for(let n=0;n<250;n++){if(f())return;await wait(40);}throw Error('timeout');};
 const submit=async(selector,values={})=>{const f=document.querySelector(selector);if(!f)throw Error('missing '+selector);for(const[k,v]of Object.entries(values)){if(f.elements[k].type==='checkbox')f.elements[k].checked=v;else f.elements[k].value=v;}f.requestSubmit();await until(()=>!inFlight);};
 await rpc('register',{name:'Active Dialogue Parent',password:'qa-dialogue-parent',role:'PARENT'});
 const c=await rpc('register',{name:'Active Dialogue Child',password:'qa-dialogue-child',role:'STUDENT',profile:{region:'Region',city:'City',school:'School',grade:7,address:{mode:'manual'}}});
 await rpc('save_provider',{config:{kind:'ollama',model:'synthetic-only',revision:0,endpoint:window.__qaEndpoint}});
 await rpc('logout');await rpc('login',{account:c.id,password:'qa-dialogue-child'});await refresh();
 navigate('homework');selectLearningSubject('algebra');await learnRefresh();render();
 await submit('[data-learning-form="work"]');const work=learnData().works.at(-1).work;
 await submit('[data-learning-form="work_revision"]',{value:'3x+5=20\n3x=15\nx=5',confirm:true});
 const accepted=[],started=performance.now();
 for(let i=0;i<3;i++){
   if(i)await wait(60000);
   await submit('[data-learning-form="work_check"]',{intent:'follow_up',follow_up:'Поясни шаг '+(i+1)});
   const job=learnData().jobs.find(j=>j.body.kind==='work_check').id;
   let completed=false;
   for(let n=0;n<250;n++){const j=await rpc('learning',{action:'job',job});if(j.status==='succeeded'){completed=true;break;}if(!['pending','running'].includes(j.status))throw Error(JSON.stringify(j));await wait(40);}
   if(!completed)throw Error('job did not finish');
   accepted.push({request:i+1,elapsed_ms:performance.now()-started,status:'succeeded'});
   await learnRefresh();render();
 }
 await wait(70000);await refresh();await learnRefresh();render();
 const sessions=student().sessions.filter(s=>s.homework===work);
 window.__testResult={passed:true,meaning:'Reproduction completed; active_dialogue_preserved=false is product failure',version:state.status.version,
   accepted,observed_ms:performance.now()-started,last_successful_request_age_ms:performance.now()-started-accepted.at(-1).elapsed_ms,
   sessions:sessions.map(s=>({id:s.id,status:s.status,seconds:s.seconds})),active_dialogue_preserved:sessions.length===1&&sessions[0].status==='active',daily_seconds:student().daily.seconds};
}catch(error){window.__testResult={passed:false,error:error.stack};}})();
