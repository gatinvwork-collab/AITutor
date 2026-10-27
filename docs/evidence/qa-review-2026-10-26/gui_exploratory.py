"""Independent Qt GUI probes, uses only synthetic profiles and FakeProvider."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tests import gui_feedback_03 as harness

import uuid
harness.ROOT = Path(__file__).resolve().parents[3] / "build" / ("qa-review-gui-" + uuid.uuid4().hex[:8])
harness.SCRIPT = r"""
(async()=>{
  const checks=[];
  const check=(id,expected,actual)=>checks.push({id,expected,actual,passed:expected===actual});
  const until=async fn=>{for(let n=0;n<300;n++){if(fn())return;await new Promise(r=>setTimeout(r,40));}throw Error('timeout');};
  const shot=async name=>{window.__capture=name;await until(()=>window.__captured===name);};
  try {
    const p=await rpc('register',{name:'QA Parent A',password:'qa-parent-password',role:'PARENT'});
    const p2=await rpc('register',{name:'QA Parent B',password:'qa-parent-password',role:'PARENT'});
    const c=await rpc('register',{name:'QA Student',password:'qa-child-password',role:'STUDENT',
      profile:{region:'Region',city:'City',school:'School',grade:7,address:{mode:'manual'}}});
    await rpc('save_provider',{config:{kind:'ollama',model:'qa-mock-only',revision:0}});
    const backup=await rpc('backup',{password:'qa-backup-password'});
    await rpc('logout');await rpc('login',{account:c.id,password:'qa-child-password'});await refresh();
    state.lesson=await rpc('start_lesson',{topic_id:'math-equations'});
    state.route='lesson';render();
    const draft=document.querySelector('#answer-draft');draft.value='QA DRAFT';draft.dispatchEvent(new Event('input',{bubbles:true}));
    state.route='settings';render();
    const theme=document.querySelector('form[data-form="theme"]');
    theme.elements.design.value='strict';theme.elements.design.dispatchEvent(new Event('change',{bubbles:true}));
    theme.requestSubmit();await until(()=>!inFlight&&state.data.user.design==='strict');
    check('theme_save_explicit_success',true,document.querySelector('#notice').classList.contains('show')&&document.querySelector('#notice').textContent.length>0);
    state.route='lesson';render();check('lesson_draft_survives_theme', 'QA DRAFT', document.querySelector('#answer-draft').value);
    const routes=['home','subjects','lesson','homework','knowledge','history','program','settings'];
    const overflow=[];
    for(const design of ['strict','modern'])for(const theme of ['light','dark']){
      await rpc('set_theme',{theme,design});await refresh();
      for(const route of routes){state.route=route;render();if(document.documentElement.scrollWidth>innerWidth)overflow.push(design+'/'+theme+'/'+route);}
    }
    check('student_screens_overflow',0,overflow.length);
    await rpc('pause',{session:state.lesson.id});const sessionId=state.lesson.id;
    await rpc('logout');await rpc('login',{account:p.id,password:'qa-parent-password'});await refresh();
    const parentOverflow=[];
    const parentRoutes=['home','students','notifications','knowledge','history','controls','program','providers','backup','security','settings'];
    const profile=await rpc('get_profile',{account:p.id});
    await rpc('save_profile',{account:p.id,revision:profile.revision,changes:{name:'ДлинноеИмя'.repeat(6)}});
    for(const design of ['strict','modern'])for(const theme of ['light','dark']){
      await rpc('set_theme',{theme,design});await refresh();
      for(const route of parentRoutes){state.route=route;render();if(document.documentElement.scrollWidth>innerWidth)parentOverflow.push(design+'/'+theme+'/'+route);}
      check('parent_appearance_'+design+'_'+theme,design,document.body.dataset.design);
    }
    check('parent_screens_with_long_name_overflow',0,parentOverflow.length);
    state.selected=c.id;state.route='history';render();
    document.querySelector('[data-action="open-session"][data-value="'+sessionId+'"]').click();
    await until(()=>!inFlight&&!!state.report);
    check('parent_report_opened',sessionId,state.report.id);
    state.route='backup';render();const form=document.querySelector('form[data-form="restore"]');
    form.elements.filename.value=backup.file;form.elements.password.value='qa-backup-password';
    form.elements.account.value=p.id;form.elements.account_password.value='qa-parent-password';
    form.querySelector('input[type="checkbox"]').checked=true;
    state.authMode='login';form.requestSubmit();await until(()=>!inFlight&&!state.data);
    const login=document.querySelector('form[data-form="login"]');
    login.elements.account.value=p2.id;login.elements.password.value='qa-parent-password';login.requestSubmit();
    await until(()=>!inFlight&&state.data?.user.id===p2.id);
    check('unrelated_parent_has_no_students',0,state.data.students.length);
    state.route='history';render();
    check('restore_clears_other_family_cached_report',false,document.querySelector('.content').textContent.includes('Разберём тему по шагам.'));
    await shot('cached-report-after-restore');
    window.__testResult={passed:checks.every(c=>c.passed),checks};
  }catch(error){window.__testResult={passed:false,error:error.stack,checks};}
})();
"""
if __name__ == "__main__":
    raise SystemExit(harness.main())
