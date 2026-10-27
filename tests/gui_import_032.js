(async()=>{
  const checks=[];
  const check=(id,passed)=>{checks.push({id,passed:!!passed});if(!passed)throw Error(id);};
  const until=async fn=>{for(let n=0;n<400;n++){if(fn())return;await new Promise(r=>setTimeout(r,40));}throw Error('UI timeout');};
  try {
    let child;
    if(window.__qaLogin){child=window.__qaLogin;await rpc('login',{account:child.id,password:child.password});}
    else {
      await rpc('register',{name:'Import parent',password:'import-parent-password',role:'PARENT'});
      child=await rpc('register',{name:'Import child',password:'import-child-password',role:'STUDENT',
        profile:{region:'Region',city:'City',school:'School',grade:7,address:{mode:'manual'}}});
      await rpc('logout');await rpc('login',{account:child.id,password:'import-child-password'});
    }
    await refresh();state.hwSubject='algebra';state.route='homework';render();
    if(window.__qaUsePicker){
      document.querySelector('[data-action="file"]').click();await until(()=>!inFlight&&!!state.homework);
      const savedId=state.homework.id, count=(await rpc('snapshot')).students[0].homework.length;
      document.querySelector('[data-action="file"]').click();await until(()=>!inFlight);
      check('long-picker-file-refused',document.querySelector('#notice').textContent.includes('Разбейте'));
      check('failed-import-keeps-existing-work',state.homework.id===savedId&&(await rpc('snapshot')).students[0].homework.length===count);
      document.querySelector('[data-action="file"]').click();await until(()=>!inFlight);
      check('cancel-picker-keeps-existing-work',state.homework.id===savedId);
    }
    state.homework=null;delete state.drafts['homework-draft'];render();
    const field=document.querySelector('#homework-draft');
    field.value='😀'.repeat(30000);field.dispatchEvent(new Event('input',{bubbles:true}));
    check('unicode-30000-valid',field.checkValidity()&&field.value.length===60000);
    const manual=await rpc('prepare_homework',{subject:'algebra'});
    await rpc('confirm_homework',{homework:manual.id,text:field.value});
    field.value+='😀';field.dispatchEvent(new Event('input',{bubbles:true}));
    check('unicode-30001-invalid',!field.checkValidity());
    let error;
    try{await rpc('confirm_homework',{homework:manual.id,text:field.value});}catch(e){error=e;}
    check('unicode-native-boundary',!!error);
    const before=await rpc('snapshot');const old=before.students[0].homework.find(h=>h.id==='legacy-long032');
    state.homework=old;state.drafts['homework-draft']=old.text;render();
    document.querySelector('form[data-form="homework"] input[name="confirmed"]').checked=true;
    document.querySelector('form[data-form="homework"]').requestSubmit();await until(()=>!inFlight);
    check('legacy-long-ui-refused',document.querySelector('#notice').textContent.includes('Разбейте'));
    check('legacy-long-no-new-version',(await rpc('snapshot')).students[0].homework.length===before.students[0].homework.length);
    const short=before.students[0].homework.find(h=>h.id==='legacy-short032');
    state.homework=short;state.drafts['homework-draft']=short.text;render();
    document.querySelector('form[data-form="homework"] input[name="confirmed"]').checked=true;
    document.querySelector('form[data-form="homework"]').requestSubmit();await until(()=>!inFlight);
    check('legacy-short-new-version',state.homework.id!==short.id&&state.homework.previous_homework===short.id);
    check('legacy-full-text-visible',document.querySelector('#homework-draft').value.length===6000);
    check('legacy-text-needs-explicit-review',!document.querySelector('form[data-form="homework"] input[name="confirmed"]').checked&&!state.homework.confirmed);
    const snapshot=await rpc('snapshot');const prior=snapshot.students[0].homework.find(h=>h.id===short.id);
    check('legacy-original-result-preserved',prior.text.length===5000&&prior.result==='Старый результат');
    window.__testResult={passed:true,checks};
  }catch(error){window.__testResult={passed:false,error:error.stack,checks};}
})();
