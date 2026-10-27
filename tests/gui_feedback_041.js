(async()=>{const checks=[];try{
 const check=(name,ok)=>{checks.push({name,ok:!!ok});if(!ok)throw Error(name);};
 const wait=ms=>new Promise(r=>setTimeout(r,ms));
 const shot=async name=>{window.__capture=name;for(let i=0;i<100;i++){if(window.__captured===name)return;await wait(40);}throw Error('capture timeout');};
 await shot('brand-welcome');
 const parent=await rpc('register',{name:'Parent no AI',password:'qa-feedback-parent-password',role:'PARENT'});
 const child=await rpc('register',{name:'Student no AI',password:'qa-feedback-child-password',role:'STUDENT',profile:{region:'Region',city:'City',school:'School',grade:7,address:{mode:'manual'}}});
 await refresh();
 for(const subject of Object.keys(subjects)){
  navigate('home');document.querySelector(`[data-action="subject"][data-value="${subject}"]`).click();
  check('parent-auxiliary-catalog-'+subject,state.route==='subjects'&&state.subject===subject);
  check('parent-auxiliary-origin-'+subject,document.querySelector('nav [aria-current="page"]').dataset.value==='home');
 }
 for(const role of ['PARENT','STUDENT']){
  if(role==='STUDENT'){await rpc('logout');await rpc('login',{account:child.id,password:'qa-feedback-child-password'});await refresh();}
  for(const design of ['strict','modern'])for(const theme of ['light','dark','system']){
   await rpc('set_theme',{design,theme});await refresh();
   if(role==='PARENT'&&((design==='strict'&&theme==='light')||(design==='modern'&&theme==='dark'))){navigate('home');await shot(`brand-${design}-${theme}`);}
   const nav=role==='PARENT'?parentNav:studentNav;
   for(const [route] of nav){
    const button=document.querySelector(`nav [data-value="${route}"]`),oldShell=document.querySelector('.sidebar');
    button.focus();button.click();
    check(`${role}-${design}-${theme}-${route}-route`,state.route===route&&document.querySelector('nav [aria-current="page"]')===button);
    check(`${role}-${design}-${theme}-${route}-stable-focus`,document.activeElement===button&&document.querySelector('.sidebar')===oldShell);
   }
  }
  navigate('history');const filter=document.querySelector('#history-subject');filter.focus();
  filter.value='physics';filter.dispatchEvent(new Event('change',{bubbles:true}));
  check(role+'-filter-focus-restored',document.activeElement.id==='history-subject');
  const before=state.route;navigate('not-a-route');check(role+'-unknown-route-rejected',state.route===before);
 }
 await rpc('logout');await rpc('login',{account:parent.id,password:'qa-feedback-parent-password'});await refresh();
 const request=bridge.request.bind(bridge);let release;
 bridge.request=(id,command,payload)=>{if(command==='snapshot'&&!release)release=()=>request(id,command,payload);else request(id,command,payload);};
 const operation=perform(async()=>{await rpc('snapshot');operationRoute('students');await refresh();});
 check('busy-navigation-remains-enabled',[...document.querySelectorAll('nav button')].every(b=>!b.disabled));
 for(const route of ['notifications','home','history'])document.querySelector(`nav [data-value="${route}"]`).click();
 check('busy-last-navigation-visible',state.route==='history');
 check('busy-mutations-disabled',[...document.querySelectorAll('.content button')].every(b=>b.disabled));
 release();await operation;bridge.request=request;
 check('late-operation-does-not-steal-route',state.route==='history');
 check('busy-buttons-recover',[...document.querySelectorAll('nav button')].every(b=>!b.disabled));
 navigate('notifications');await perform(()=>openProfile(child.id));
 check('profile-return-highlights-origin',document.querySelector('nav [aria-current="page"]').dataset.value==='notifications');
 state.profileDirty=true;const confirm=window.confirm;window.confirm=()=>false;
 document.querySelector('nav [data-value="home"]').click();window.confirm=confirm;
 check('unsaved-profile-cancel-preserves-screen',state.route==='profile'&&state.profileDirty);
 state.profileDirty=false;document.querySelector('[data-action="cancel-profile"]').click();
 check('profile-cancel-returns-origin',state.route==='notifications');
 check('brand-resource-loaded',document.querySelector('.brand-lockup img').naturalWidth>0&&document.querySelector('.brand-wordmark').textContent==='Tutor-AI');
 await rpc('logout');await refresh();
 check('logout-removes-shell-identity',!document.querySelector('#app').hasAttribute('data-shell')&&!state.data);
 await wait(150);window.__testResult={passed:true,checks};
}catch(e){window.__testResult={passed:false,error:e.stack,checks};}})();
