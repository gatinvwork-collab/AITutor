(async()=>{const checks=[];try{
 const check=(id,passed)=>{checks.push({id,passed:!!passed});if(!passed)throw Error(id);};
 const until=async f=>{for(let n=0;n<400;n++){if(f())return;await new Promise(r=>setTimeout(r,40));}throw Error('UI timeout');};
 let child;
 if(window.__qaLogin){child=window.__qaLogin;await rpc('login',{account:child.id,password:child.password});}
 else {await rpc('register',{name:'Import parent',password:'import-parent-password',role:'PARENT'});child=await rpc('register',{name:'Import child',password:'import-child-password',role:'STUDENT',profile:{region:'Region',city:'City',school:'School',grade:7,address:{mode:'manual'}}});await rpc('logout');await rpc('login',{account:child.id,password:'import-child-password'});}
 await refresh();selectLearningSubject('algebra');state.route='homework';await learnRefresh();render();
 const work=await learnCall('work',{student:child.id,subject:'algebra'});await learnRefresh();render();
 if(window.__qaUsePicker){
   document.querySelector('[data-learning="work_original"]').click();await until(()=>!inFlight&&learnData().works.at(-1).revision===1);
   const row=learnData().works.at(-1),id=row.body.originals[0],count=(await rpc('snapshot')).students[0].homework.length;
   document.querySelector('[data-learning="work_original"]').click();await until(()=>!inFlight);
   check('long-picker-file-refused',document.querySelector('#notice').textContent.includes('Разбейте'));
   check('failed-import-keeps-existing-work',learnData().works.at(-1).body.originals[0]===id&&(await rpc('snapshot')).students[0].homework.length===count);
   document.querySelector('[data-learning="work_original"]').click();await until(()=>!inFlight);
   check('cancel-picker-keeps-existing-work',learnData().works.at(-1).body.originals[0]===id);
 }
 const f=document.querySelector('[data-learning-form="work_revision"]'),field=f.elements.value;
 field.value='😀'.repeat(30000);field.dispatchEvent(new Event('input',{bubbles:true}));check('unicode-30000-valid',field.checkValidity()&&field.value.length===60000);
 const revision=learnData().works.at(-1).revision;
 await learnCall('work_revision',{work:work.id,value:field.value,expected_revision:revision,confirm:false});
 field.value+='😀';field.dispatchEvent(new Event('input',{bubbles:true}));check('unicode-30001-invalid',!field.checkValidity());
 let error;try{await learnCall('work_revision',{work:work.id,value:field.value,expected_revision:revision+1,confirm:false});}catch(e){error=e;}
 check('unicode-native-boundary',!!error);
 const before=await rpc('snapshot');
 error=null;try{await rpc('prepare_homework',{subject:'algebra',homework:'legacy-long032'});}catch(e){error=e;}
 check('legacy-long-refused',!!error&&error.message.includes('Разбейте'));
 check('legacy-long-no-new-version',(await rpc('snapshot')).students[0].homework.length===before.students[0].homework.length);
 const short=await rpc('prepare_homework',{subject:'algebra',homework:'legacy-short032'});
 check('legacy-short-new-version',short.id!=='legacy-short032'&&short.previous_homework==='legacy-short032');
 check('legacy-full-text-visible',short.text.length===6000);
 check('legacy-text-needs-explicit-review',!short.confirmed);
 const prior=(await rpc('snapshot')).students[0].homework.find(h=>h.id==='legacy-short032');
 check('legacy-original-result-preserved',prior.text.length===5000&&prior.result==='Старый результат');
 window.__testResult={passed:true,checks};
}catch(error){window.__testResult={passed:false,error:error.stack,checks};}})();
