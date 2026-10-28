(async()=>{
 const checks=[];const check=(name,ok)=>{checks.push({name,ok:!!ok});if(!ok)throw Error(name);};
 const wait=ms=>new Promise(r=>setTimeout(r,ms));
 const click=selector=>{const e=document.querySelector(selector);if(!e)throw Error(selector);e.click();};
 const settle=async()=>{for(let i=0;i<300;i++){await wait(100);if(!inFlight)return;}throw Error('operation timeout');};
 try{
  check('empty welcome with native transfer action',!state.status.exists&&!!document.querySelector('[data-action="choose-transfer"]'));
  click('[data-action="choose-transfer"]');await settle();
  check('source and destination preview',!!state.transferPlan&&state.transferPlan.source.includes('app-data')&&state.transferPlan.accounts.length===2);
  let form=document.querySelector('[data-form="transfer"]');
  form.querySelector('[name="account"]').value=window.__transferLogin.id;
  form.querySelector('[name="password"]').value='incorrect';form.querySelector('[type="checkbox"]').checked=true;
  form.requestSubmit();await settle();
  check('failed password never publishes success',!state.status.exists&&!state.transferDone&&!!document.querySelector('[data-form="transfer"]'));
  click('[data-action="recover-transfer"]');await settle();
  check('safe cleanup returns to blank welcome',!state.status.exists&&!state.transferPlan);
  click('[data-action="choose-transfer"]');await settle();
  form=document.querySelector('[data-form="transfer"]');form.querySelector('[name="account"]').value=window.__transferLogin.id;
  form.querySelector('[name="password"]').value=window.__transferLogin.password;form.querySelector('[type="checkbox"]').checked=true;
  form.requestSubmit();await settle();
  check('successful transfer requires fresh login',state.status.exists&&!state.status.authenticated&&state.status.accounts.some(a=>a.id===window.__transferLogin.id));
  await rpc('login',{account:window.__transferLogin.id,password:window.__transferLogin.password});await refresh();
  check('original family and profile names',state.data.user.name==='Родитель AI-Tutor'&&state.data.students[0].name==='Старый ученик');
  check('native branding and version',state.status.version===window.__expectedVersion);
  check('history remains verbatim',state.data.students[0].homework.some(h=>h.text==='AI-Tutor history remains'));
  state.route='settings';render();applyAppearance('dark','modern');
  check('modern dark theme',document.body.dataset.design==='modern'&&document.body.dataset.theme==='dark');
  window.__testResult={passed:true,checks,capture:'transfer-success'};
 }catch(e){window.__testResult={passed:false,checks,error:e.message,stack:e.stack};}
})();
