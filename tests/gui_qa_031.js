/* Shared by source-WebView and compiled-exe acceptance, synthetic data only. */
(async()=>{
  const checks=[];
  const check=(id,ok)=>{checks.push({id,passed:!!ok});if(!ok)throw Error(id);};
  const until=async fn=>{for(let n=0;n<450;n++){if(fn())return;await new Promise(r=>setTimeout(r,40));}throw Error('UI timeout');};
  const pause=ms=>new Promise(r=>setTimeout(r,ms));
  const secret='PRIVATE-QA031-MARKER';
  try {
    const a=await rpc('register',{name:'QA031 Parent A',password:'qa031-parent-password',role:'PARENT'});
    const b=await rpc('register',{name:'QA031 Parent B',password:'qa031-parent-password',role:'PARENT'});
    const c=await rpc('register',{name:'QA031 Child',password:'qa031-child-password',role:'STUDENT',
      profile:{region:'Region',city:'City',school:'School',grade:7,address:{mode:'manual'}}});
    await rpc('save_provider',{config:{kind:'ollama',model:'qa031-only',endpoint:window.__qaEndpoint||'http://127.0.0.1:11434',revision:0}});
    const backup=await rpc('backup',{password:'qa031-backup-password'});
    await rpc('logout');await rpc('login',{account:c.id,password:'qa031-child-password'});await refresh();
    // Source harness uses FakeProvider; compiled exe uses a local HTTP stub.
    state.lesson=await rpc('start_lesson',{topic_id:'math-equations'});state.route='lesson';render();
    const lessonId=state.lesson.id;
    document.querySelector('#answer-draft').value=secret;
    document.querySelector('#answer-draft').dispatchEvent(new Event('input',{bubbles:true}));
    for(const design of ['strict','modern'])for(const theme of ['system','light','dark']){
      state.route='settings';render();const form=document.querySelector('form[data-form="theme"]');
      document.querySelector('#notice').classList.remove('show');
      form.elements.design.value=design;form.elements.theme.value=theme;
      form.elements.design.dispatchEvent(new Event('change',{bubbles:true}));
      check('preview-is-not-save-'+design+'-'+theme,!document.querySelector('#notice').classList.contains('show'));
      form.requestSubmit();await until(()=>!inFlight);
      check('save-confirmation-'+design+'-'+theme,document.querySelector('#notice').textContent==='Оформление сохранено');
    }
    state.route='lesson';render();check('draft-survives-appearance',document.querySelector('#answer-draft').value===secret);
    const savedTheme=state.data.user.theme,savedDesign=state.data.user.design;
    state.route='settings';render();let form=document.querySelector('form[data-form="theme"]');
    form.elements.theme.value=savedTheme==='light'?'dark':'light';form.elements.theme.dispatchEvent(new Event('change',{bubbles:true}));
    state.route='lesson';render();
    check('unsaved-theme-reverts',document.body.dataset.colorPreference===savedTheme&&state.data.user.design===savedDesign);
    // Fail only the IPC reply: native rollback is checked independently by pytest.
    const realRequest=bridge.request;
    bridge.request=(id,command,args)=>command==='set_theme'?
      setTimeout(()=>receiveResponse(id,JSON.stringify({error:'QA031 simulated write failure'})),0):realRequest(id,command,args);
    state.route='settings';render();form=document.querySelector('form[data-form="theme"]');
    form.elements.theme.value='light';form.requestSubmit();await until(()=>!inFlight);
    check('failed-theme-no-success',document.querySelector('#notice').textContent.includes('simulated write failure'));
    check('failed-theme-choice-retained',document.querySelector('form[data-form="theme"]').elements.theme.value==='light');
    bridge.request=realRequest;
    form.requestSubmit();await until(()=>!inFlight);
    check('theme-retry-works',state.data.user.theme==='light'&&document.querySelector('#notice').textContent==='Оформление сохранено');
    await rpc('pause',{session:lessonId});
    await rpc('logout');await rpc('login',{account:a.id,password:'qa031-parent-password'});await refresh();
    state.selected=c.id;state.route='history';render();
    document.querySelector('[data-action="open-session"][data-value="'+lessonId+'"]').click();await until(()=>!inFlight&&state.report?.id===lessonId);
    // Dirty caches and a delayed reply from the previous context must disappear.
    Object.assign(state,{homework:{id:'old-work',filename:secret},homeworkResult:secret,codeResult:secret,
      providerResult:secret,profileEdit:await rpc('get_profile',{account:c.id}),drafts:{'answer-draft':secret}});
    document.querySelector('#secret-value').textContent=secret;notify(secret);
    let delayedId,lateRejected=false;
    bridge.request=(id,command,args)=>command==='search_addresses'?(delayedId=id):realRequest(id,command,args);
    const delayed=rpc('search_addresses',{kind:'region',query:'QA'}).then(()=>{state.providerResult=secret;}).catch(error=>{lateRejected=error.stale;});
    state.route='backup';render();form=document.querySelector('form[data-form="restore"]');
    form.elements.filename.value=backup.file;form.elements.password.value='qa031-backup-password';
    form.elements.account.value=a.id;form.elements.account_password.value='qa031-parent-password';
    form.querySelector('input[type="checkbox"]').checked=true;form.requestSubmit();
    await until(()=>!inFlight&&!state.data);await delayed;
    check('old-rpc-rejected',lateRejected&&!pending.has(delayedId));
    check('restore-clears-personal-memory',!JSON.stringify(state).includes(secret)&&document.querySelector('#secret-value').textContent==='');
    check('restore-clears-dom',!document.body.textContent.includes(secret));
    bridge.request=realRequest;
    form=document.querySelector('form[data-form="login"]');form.elements.account.value=b.id;form.elements.password.value='qa031-parent-password';
    form.requestSubmit();await until(()=>!inFlight&&state.data?.user.id===b.id);
    receiveResponse(delayedId,JSON.stringify({result:{text:secret}}));await pause(50);
    state.route='history';render();
    check('unrelated-parent-no-report',state.data.students.length===0&&!state.report&&!document.body.textContent.includes('Разберём'));
    check('late-reply-cannot-repopulate',!JSON.stringify(state).includes(secret));
    await rpc('logout');await rpc('login',{account:a.id,password:'qa031-parent-password'});await refresh();
    state.route='history';render();
    check('same-parent-missing-session-stays-missing',!state.report&&!student().sessions.some(s=>s.id===lessonId));
    // A stale object must also fail closed on an ordinary render of a fresh snapshot.
    state.report={id:lessonId,title:secret,messages:[{text:secret}]};render();
    check('render-resolves-only-authorized-report',!state.report&&!document.body.textContent.includes(secret));
    const context=nativeContext;
    state.route='backup';render();form=document.querySelector('form[data-form="restore"]');
    form.elements.filename.value='does-not-exist.aitbackup';form.elements.password.value='qa031-backup-password';
    form.elements.account.value=a.id;form.elements.account_password.value='qa031-parent-password';
    form.querySelector('input[type="checkbox"]').checked=true;form.requestSubmit();await until(()=>!inFlight);
    check('failed-restore-preserves-context',state.data?.user.id===a.id&&nativeContext===context&&state.route==='backup');
    window.__testResult={passed:true,checks};
  }catch(error){window.__testResult={passed:false,error:error.stack,checks};}
})();
