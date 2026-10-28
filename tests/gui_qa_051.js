(async()=>{const checks=[];try{
 const check=(name,ok)=>{checks.push({name,ok:!!ok});if(!ok)throw Error(name);};
 const wait=ms=>new Promise(r=>setTimeout(r,ms));
 const until=async f=>{for(let n=0;n<300;n++){if(f())return;await wait(40);}throw Error('condition timeout');};
 const submit=async(selector,values={})=>{const f=document.querySelector(selector);if(!f)throw Error('missing '+selector);for(const [k,v]of Object.entries(values)){f.elements[k].value=v;f.elements[k].dispatchEvent(new Event('input',{bubbles:true}));}f.requestSubmit();await until(()=>!inFlight);};
 const parent=await rpc('register',{name:'QA051 Parent',password:'qa051-parent-password',role:'PARENT'});
 const child=await rpc('register',{name:'QA051 Child',password:'qa051-child-password',role:'STUDENT',profile:{region:'Region',city:'City',school:'School',grade:7,address:{mode:'manual'}}});
 await rpc('logout');await rpc('login',{account:child.id,password:'qa051-child-password'});await refresh();
 for(const subject of Object.keys(subjects)){
   state.learnSubject=subject==='algebra'?'physics':'algebra';navigate('subjects');
   document.querySelector(`[data-action="subject"][data-value="${subject}"]`)?.click();
   // The overview card and the subject switcher use the same subject action.
   check('subject action '+subject,state.subject===subject);
   document.querySelector('[data-action="subject-homework"]').click();
   if(!learnData())await learnRefresh();render();
   check('selected '+subject,document.querySelector('#learn-subject').value===subject);
   await submit('[data-learning-form="work"]');
   const row=learnData().works.at(-1);check('stored '+subject,row.body.subject===subject);
   const form=document.querySelector(`[data-learning-form="work_revision"] input[name="work"][value="${row.work}"]`).form;
   form.elements.value.value=subject==='informatics'?'print(1)':'draft '+subject;form.elements.value.dispatchEvent(new Event('input',{bubbles:true}));
   const select=document.querySelector('#learn-subject');select.value=subject==='geometry'?'physics':'geometry';select.dispatchEvent(new Event('change',{bubbles:true}));
   document.querySelector('#learn-subject').value=subject;document.querySelector('#learn-subject').dispatchEvent(new Event('change',{bubbles:true}));
   check('draft kept '+subject,document.querySelector(`[data-learning-form="work_revision"] input[value="${row.work}"]`).form.elements.value.value.includes(subject==='informatics'?'print':'draft'));
   document.querySelector(`[data-learning-form="work_revision"] input[value="${row.work}"]`).form.querySelector('[data-learning="discard_draft"]').click();await until(()=>!inFlight);
   check('explicit discard '+subject,document.querySelector(`[data-learning-form="work_revision"] input[value="${row.work}"]`).form.elements.value.value==='');
   const python=[...document.querySelectorAll('[data-learning="analyze"]')].filter(b=>b.dataset.id===row.work);
   check('python scope '+subject,python.length===(subject==='informatics'?1:0));
 }
 state.learning=null;state.learnSubject='algebra';render();
 const originalRPC=rpc;let release;const gate=new Promise(r=>release=r);
 rpc=async(command,args)=>{if(command==='learning'&&args.action==='overview')await gate;return originalRPC(command,args);};
 const loading=perform(async()=>{await learnRefresh();render();});
 const select=document.querySelector('#learn-subject');check('subject usable while loading',!select.disabled);
 select.value='physics';select.dispatchEvent(new Event('change',{bubbles:true}));release();await loading;rpc=originalRPC;
 check('late load does not undo selection',document.querySelector('#learn-subject').value==='physics');
 selectLearningSubject('not-a-subject');render();check('invalid requires explicit choice',!document.querySelector('[data-learning-form="work"]'));
 selectLearningSubject('algebra');render();
 const assignment=document.querySelector('[data-learning-form="assignment"]');assignment.elements.title.value='UNSAVED BOOK';assignment.elements.title.dispatchEvent(new Event('input',{bubbles:true}));
 selectLearningSubject('geometry');render();selectLearningSubject('algebra');render();
 check('book draft scoped',document.querySelector('[data-learning-form="assignment"]').elements.title.value==='UNSAVED BOOK');
 await rpc('logout');await rpc('login',{account:child.id,password:'qa051-child-password'});await refresh();navigate('learning');await learnRefresh();render();
 check('logout clears drafts',document.querySelector('[data-learning-form="assignment"]').elements.title.value!=='UNSAVED BOOK');
 check('old subjects unchanged',learnData().works.filter(w=>w.revision===0).every(w=>Object.hasOwn(subjects,w.body.subject)));
 window.__testResult={passed:true,checks};
}catch(error){window.__testResult={passed:false,error:error.stack,checks};}})();
