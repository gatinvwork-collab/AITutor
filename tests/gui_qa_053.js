(async()=>{const checks=[];try{
 const wait=ms=>new Promise(r=>setTimeout(r,ms));
 const check=(name,ok)=>{checks.push({name,ok:!!ok});if(!ok)throw Error(name);};
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
   await submit('[data-learning-form="work_check"]',{intent:['check','hint','follow_up'][i],follow_up:'Поясни шаг '+(i+1)});
   const job=learnData().jobs.find(j=>j.body.kind==='work_check').id;
   let completed=false;
   for(let n=0;n<250;n++){const j=await rpc('learning',{action:'job',job});if(j.status==='succeeded'){completed=true;break;}if(!['pending','running'].includes(j.status))throw Error(JSON.stringify(j));await wait(40);}
   check('request '+(i+1)+' accepted',completed);
   accepted.push({request:i+1,elapsed_ms:performance.now()-started,status:'succeeded'});
   await learnRefresh();render();
 }
 await wait(70000);await refresh();await learnRefresh();render();
 let sessions=student().sessions.filter(s=>s.homework===work);
 const observed={at_ms:performance.now()-started,last_success_age_ms:performance.now()-started-accepted.at(-1).elapsed_ms,
   sessions:sessions.map(s=>({id:s.id,status:s.status,seconds:s.seconds})),daily_seconds:student().daily.seconds};
 const active_dialogue_preserved=sessions.length===1&&sessions[0].status==='active';
 check('real dialogue remains one active lesson after 60/60/70',active_dialogue_preserved);
 check('time exceeds obsolete 180-second window',sessions[0].seconds>185);
 check('daily equals linked lesson',Math.abs(student().daily.seconds-sessions[0].seconds)<0.000001);
 check('all three turns retained',learnData().calls.filter(c=>c.work===work).length===3);
 // Observe near the real idle boundary; only polling/reading occurs now.
 await wait(Math.max(0,178000-(performance.now()-started-accepted.at(-1).elapsed_ms)));
 await refresh();sessions=student().sessions.filter(s=>s.homework===work);
 const near_idle={age_ms:performance.now()-started-accepted.at(-1).elapsed_ms,status:sessions[0].status,seconds:sessions[0].seconds};
 check('still active near 178 seconds after last response',sessions.length===1&&sessions[0].status==='active');
 await wait(10000);await refresh();await learnRefresh();render();sessions=student().sessions.filter(s=>s.homework===work);
 const actual_idle={age_ms:performance.now()-started-accepted.at(-1).elapsed_ms,status:sessions[0].status,seconds:sessions[0].seconds,daily_seconds:student().daily.seconds};
 check('true idle eventually pauses despite polling',sessions.length===1&&sessions[0].status==='paused');
 check('true idle remains bounded to last action',sessions[0].seconds>295&&sessions[0].seconds<310);
 check('daily agrees after idle',Math.abs(student().daily.seconds-sessions[0].seconds)<0.000001);
 await wait(6000);await refresh();
 check('paused time does not grow',student().sessions.find(s=>s.id===sessions[0].id).seconds===sessions[0].seconds);
 window.__testResult={passed:true,version:state.status.version,checks,accepted,active_dialogue_preserved,observed,near_idle,actual_idle};
}catch(error){window.__testResult={passed:false,error:error.stack,checks};}})();
