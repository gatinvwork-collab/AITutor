/* Timer boundary and retryable answer, synthetic data only. */
(async()=>{
  const checks=[];
  const check=(id,passed)=>{checks.push({id,passed:!!passed});if(!passed)throw Error(id);};
  const until=async fn=>{for(let n=0;n<500;n++){if(fn())return;await new Promise(r=>setTimeout(r,40));}throw Error('UI timeout');};
  try {
    await rpc('register',{name:'Timer parent',password:'timer-parent-password',role:'PARENT'});
    const child=await rpc('register',{name:'Timer child',password:'timer-child-password',role:'STUDENT',
      profile:{region:'Region',city:'City',school:'School',grade:7,address:{mode:'manual'}}});
    await rpc('save_provider',{config:{kind:'ollama',model:'qa-only',endpoint:window.__qaEndpoint||'http://127.0.0.1:11434',revision:0}});
    await rpc('logout');await rpc('login',{account:child.id,password:'timer-child-password'});await refresh();
    const old=await rpc('start_lesson',{topic_id:'math-equations'});await rpc('pause',{session:old.id});
    const current=await rpc('start_lesson',{topic_id:'physics-speed'});await refresh();
    const before=student().daily.seconds;
    await rpc('pause',{session:old.id});await rpc('complete',{session:old.id});
    const done=await rpc('complete',{session:old.id});await rpc('complete',{session:old.id});
    check('historical-complete-is-idempotent',done.status==='complete');
    // Two scheduler periods avoid dependence on the phase of the desktop timer.
    await new Promise(r=>setTimeout(r,11500));await refresh();
    const active=student().sessions.find(s=>s.id===current.id);
    check('historical-commands-keep-active-timer',active.status==='active'&&student().daily.seconds-before>=5);
    check('complete-date-not-rewritten',student().sessions.find(s=>s.id===old.id).ended===done.ended);
    await rpc('pause',{session:current.id});
    state.lesson=await rpc('start_lesson',{topic_id:'math-equations'});state.route='lesson';render();
    const input=document.querySelector('#answer-draft');input.value='5';input.dispatchEvent(new Event('input',{bubbles:true}));
    const real=bridge.request, operations=[];
    bridge.request=(id,command,args)=>{
      if(command==='answer'){
        operations.push(JSON.parse(args).operation_id);
        if(operations.length===1){setTimeout(()=>receiveResponse(id,JSON.stringify({error:'Synthetic write failure'})),0);return;}
      }
      return real(id,command,args);
    };
    document.querySelector('form[data-form="answer"]').requestSubmit();await until(()=>!inFlight);
    check('failed-answer-keeps-draft',document.querySelector('#answer-draft').value==='5');
    document.querySelector('form[data-form="answer"]').requestSubmit();await until(()=>!inFlight);
    bridge.request=real;
    check('retry-uses-same-operation-id',operations.length===2&&operations[0]===operations[1]);
    check('retry-advances-exactly-once',state.lesson.index===1&&state.lesson.total===1);
    check('successful-answer-clears-draft',!state.drafts['answer-draft']&&!state.answerOperation);
    window.__testResult={passed:true,checks,observations:{charged:student().daily.seconds-before}};
  }catch(error){window.__testResult={passed:false,error:error.stack,checks};}
})();
