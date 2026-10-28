(async()=>{const checks=[];try{
 const wait=ms=>new Promise(r=>setTimeout(r,ms));
 const until=async f=>{for(let n=0;n<200;n++){if(f())return;await wait(50);}throw Error('timeout');};
 const check=(name,ok)=>{checks.push({name,ok:!!ok});if(!ok)throw Error(name);};
 const submit=async(selector,values={})=>{const f=document.querySelector(selector);if(!f)throw Error('missing '+selector);for(const[k,v]of Object.entries(values)){if(f.elements[k].type==='checkbox')f.elements[k].checked=v;else f.elements[k].value=v;}f.requestSubmit();await until(()=>!inFlight);};
 await rpc('register',{name:'Copy QA Parent',password:'copy-qa-parent',role:'PARENT'});
 const c=await rpc('register',{name:'Copy QA Child',password:'copy-qa-child',role:'STUDENT',profile:{region:'Region',city:'City',school:'School',grade:7,address:{mode:'manual'}}});
 await rpc('save_provider',{config:{kind:'ollama',model:'synthetic-only',revision:0,endpoint:window.__qaEndpoint}});
 await rpc('logout');await rpc('login',{account:c.id,password:'copy-qa-child'});await refresh();
 navigate('homework');selectLearningSubject('algebra');await learnRefresh();render();
 await submit('[data-learning-form="work"]');const oldId=learnData().works.at(-1).work;
 await submit('[data-learning-form="work_revision"]',{value:'print(1)',confirm:true});
 await submit('[data-learning-form="work_check"]',{intent:'check'});
 const job=learnData().jobs[0].id;
 for(let n=0;n<200;n++){const j=await rpc('learning',{action:'job',job});if(j.status==='succeeded')break;if(!['running','pending'].includes(j.status))throw Error(JSON.stringify(j));await wait(50);}
 await learnRefresh();render();
 check('source has completed call',learnData().calls.some(x=>x.work===oldId&&x.body.status==='succeeded'));
 const originalRows=JSON.stringify(learnData().works.filter(w=>w.work===oldId)),originalCalls=JSON.stringify(learnData().calls.filter(x=>x.work===oldId));
 await submit(`[data-learning-form="work_copy"]:has(input[name="work"][value="${oldId}"])`,{subject:'informatics'});
 const copied=learnData().works.at(-1);
 check('new work ID',copied.work!==oldId);
 check('copy has chosen subject and same text',copied.body.subject==='informatics'&&copied.body.text==='print(1)');
 check('copy requires confirmation',copied.body.confirmed===false);
 check('provenance refers to source revision',copied.body.copied_from.work===oldId&&copied.body.copied_from.revision===1);
 check('source versions unchanged',JSON.stringify(learnData().works.filter(w=>w.work===oldId))===originalRows);
 check('source calls unchanged',JSON.stringify(learnData().calls.filter(x=>x.work===oldId))===originalCalls);
 check('copy has no inherited assessment calls',!learnData().calls.some(x=>x.work===copied.work));
 window.__testResult={passed:true,checks};
}catch(error){window.__testResult={passed:false,error:error.stack,checks};}})();
