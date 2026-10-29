'use strict';
// Shared data/components, distinct route composition. No copied curriculum state.
const allLearningSections=learningPage;
function scopedLearningPage(mode){
  if(!learnData())return `<h1>${mode==='program'?'Программы и запросы':'Учебный процесс'}</h1>${learningSubjectPicker()}<button data-learning="refresh">Загрузить программы и работы</button>`;
  const container=document.createElement('div');container.innerHTML=allLearningSections();
  const isParent29=state.data.user.role==='PARENT';
  if(mode==='homework')return homeworkOnly();
  const programSelectors='[data-learning-form="assignment"],[data-learning-form="curriculum"],[data-learning-form="studied"],[data-learning-form="current"],[data-learning-form="decide"]';
  for(const child of [...container.children]){
    if(child.matches('h1')){child.textContent=mode==='program'?'Программы и запросы':'Учебный процесс';continue;}
    if(child.querySelector('#learn-subject')||child.matches('label'))continue;
    if(child.matches('.row'))continue;
    const isProgram=!!child.querySelector(programSelectors)||child.querySelector('summary')?.textContent==='Родительские запросы и предпросмотр';
    if(mode==='program'?!isProgram:isProgram&&(isParent29||!!child.querySelector('[data-learning-form="assignment"],[data-learning-form="curriculum"],[data-learning-form="source"]')))child.remove();
  }
  const parent=state.data.user.role==='PARENT';
  if(mode==='learning'){
    container.querySelector('[data-learning-form="work"]')?.closest('section')?.remove();
    const link=document.createElement('p');link.innerHTML='<button data-action="route" data-value="program">Учебник, источники и запросы →</button>';container.prepend(link);
    const jobs=[...container.querySelectorAll('section')].find(s=>s.querySelector('h2')?.textContent==='Фоновые задачи');
    if(jobs)jobs.innerHTML='<h2>Фоновые задачи</h2><button data-learning="refresh">Проверить состояние задач</button>'+learnData().jobs.map(jobCard29).join('');
  }
  if(mode==='program'){
    const imports=document.createElement('section');imports.className='card';imports.innerHTML=sourceImportPanel();container.prepend(imports);
  }
  if(!parent&&mode==='learning')container.querySelector('[data-learning-form="generate"]')?.closest('section')?.querySelector('[data-learning-form="generate"]')?.remove();
  return container.innerHTML;
}
learningPage=()=>scopedLearningPage('learning');
program=()=>scopedLearningPage('program');
function homeworkOnly(){
  const d=learnData(),sid=state.learnSubject??Object.keys(subjects)[0];
  if(!d)return '<h1>Проверка ДЗ</h1>'+learningSubjectPicker()+'<button data-learning="refresh">Загрузить работы</button>';
  if(!Object.hasOwn(subjects,sid))return '<h1>Проверка ДЗ</h1>'+learningSubjectPicker()+'<p>Выберите доступный предмет.</p>';
  const selectedTopic=d.contexts?.[sid]?.topics.find(t=>t.id===state.learnTopic);
  return `<h1>Проверка ДЗ</h1>${learningSubjectPicker()}${selectedTopic?`<p>Тема: ${esc(selectedTopic.title)}</p>`:''}<p>Сохраните решение, подтвердите текст и выберите проверку, подсказку или продолжение диалога.</p><section class="card">${state.data.user.role==='STUDENT'?`<form data-learning-form="work">${learnHidden('student',d.student)}${learnHidden('subject',sid)}${selectedTopic?learnHidden('topic',selectedTopic.id):''}<button>Создать работу</button></form>`:''}${learningWorks({...d,works:d.works.filter(w=>w.body.subject===sid)},state.data.user.role==='PARENT')}</section><section class="card"><h2>Задачи ДЗ</h2>${d.jobs.filter(j=>['work_check','recognize'].includes(j.body.kind)).map(jobCard29).join('')}</section>`;
}
homeworkPage=homeworkOnly;
function jobCard29(j){return `<article><strong>${esc(j.body.kind)}</strong> · ${esc(learningLabels[j.status]||j.status)}<p>Этап: ${esc(j.body.stage||'исторические сведения отсутствуют')}</p>${j.body.code?`<p>${esc(j.body.code)} · ${esc(j.body.safe_message||'Проверьте структуру и рубрику результата; исходный ответ сохранён в журнале.')}</p>`:''}${j.body.issues?.length?`<pre>${esc(JSON.stringify(j.body.issues,null,2))}</pre>`:''}${j.body.cancel_requested?'<p>Отмена запрошена; ожидается подтверждённый исход.</p>':''}${['pending','running'].includes(j.status)?`<button data-uf29="cancel-job" data-job="${j.id}">Запросить отмену этой задачи</button>`:''}${j.body.result?jobSummary(j):''}${j.body.kind==='book_import'&&j.body.source?.hash&&['failed','cancelled','stale'].includes(j.status)?`<button data-uf29="source-resume" data-job="${j.id}">Продолжить сохранённые этапы (выбрать тот же файл)</button>`:''}</article>`;}
function sourceImportPanel(){
  const d=learnData(),sid=state.learnSubject??Object.keys(subjects)[0];if(!d)return '';
  return `<h2>Источники книги и УМК</h2><p>Ссылка в реквизитах только сохраняется. Здесь запускается отдельный ограниченный импорт PDF: до 64 МиБ / 600 страниц, до 20 выбранных страниц, OCR партиями до 4. Целая книга не сохраняется. Разрешения OCR действуют отдельно.</p><form data-uf29="import">${learnHidden('student',d.student)}${learnHidden('subject',sid)}<label>Назначение<select name="kind"><option value="book">Учебник / оглавление</option><option value="methodical">УМК / методика</option><option value="school_program">Школьная программа</option></select></label><label>HTTPS-ссылка<input name="url" type="url"></label><label>PDF-страницы (необязательно, до 20, через запятую)<input name="pages" placeholder="Поиск оглавления в начале/конце и текстовых заголовках"></label><button>Импортировать по ссылке</button><button type="button" data-uf29="local-source">Выбрать локальный PDF и импортировать</button></form>
  <h3>Проверка применимости УМК</h3><form data-uf29="match">${learnHidden('student',d.student)}<label>Книга<select name="book">${d.sources.filter(s=>s.kind==='book').map(s=>`<option value="${s.id}">${esc(s.body.title||s.hash.slice(0,12))}</option>`).join('')}</select></label><label>УМК<select name="method">${d.sources.filter(s=>s.kind==='methodical').map(s=>`<option value="${s.id}">${esc(s.body.title||s.hash.slice(0,12))}</option>`).join('')}</select></label><button>Проверить соответствие</button></form>${(d.source_matches||[]).map(m=>`<p>${esc(m.status)}: ${m.body.reasons.map(esc).join('; ')}${m.status==='compatible'?`<button type="button" data-uf29="method-skills" data-book="${m.book}" data-method="${m.method}">Предпросмотр навыков УМК</button>`:''}</p>`).join('')}
  <h3>Задачи импорта и кандидаты</h3>${d.jobs.filter(j=>j.body.kind==='book_import').map(jobCard29).join('')}`;
}
subjectPage=()=>{
  if(!state.subject)return '<h1>Предметы</h1>'+subjectCards();
  const ctx=learnData()?.contexts?.[state.subject];
  const switcher=Object.entries(subjects).map(([id,name])=>`<button data-action="subject" data-value="${id}">${esc(name)}</button>`).join('');
  if(!ctx)return `<h1>${esc(subjects[state.subject])}</h1><nav class="row">${switcher}</nav><button data-action="subject-homework" data-value="${state.subject}">Проверить ДЗ по предмету</button><button data-learning="refresh">Загрузить назначенную программу</button>`;
  return `<h1>${esc(subjects[state.subject])}</h1><nav class="row">${switcher}</nav><button data-action="subject-homework" data-value="${state.subject}">Проверить ДЗ по предмету</button>${ctx.topics.length?'':'<p>Нет опубликованной программы. Импортируйте оглавление или создайте кандидат в «Программы и запросы».</p><button data-action="route" data-value="program">Настроить программу</button>'}<div class="grid">${ctx.topics.map(t=>`<section class="card"><h2>${esc(t.title)}</h2><p>${t.optional?'Дополнительный материал · ':''}${t.studied_approved?'Прохождение подтверждено':'Прохождение не подтверждено'} · ${t.knowledge_confirmation?'Освоение подтверждено':'Освоение не подтверждено'}</p><p>${t.skills.map(s=>esc(s.title)).join('; ')}</p><button data-uf29="study" data-topic="${t.id}" data-subject="${ctx.subject}">Изучать</button><button data-uf29="topic-homework" data-topic="${t.id}" data-subject="${ctx.subject}">ДЗ</button><button data-uf29="diagnose" data-topic="${t.id}" data-subject="${ctx.subject}" ${t.allowed_actions.topic_confirmation?'':'disabled'}>Точечная диагностика</button><p>${esc(t.reasons.topic_confirmation)}</p></section>`).join('')}</div>`;
};
const originalNavigate29=navigate;
navigate=function(route){state.developerClicks=0;originalNavigate29(route);if(['subjects','knowledge','learning','homework','program'].includes(route)&&!learnData())void loadContext29();};
async function loadContext29(){try{await learnRefresh();render();}catch(e){if(!e.stale)notify(e.message);}}
document.addEventListener('click',e=>{
  const b=e.target.closest('[data-uf29]');if(!b||b.disabled)return;
  const action=b.dataset.uf29;if(action==='cancel-job'){
    perform(async()=>{const result=await learnCall('cancel_job',{job:b.dataset.job});notify(result.cancel_requested?'Отмена запрошена. Дождитесь подтверждённого результата.':'Задача уже завершена.');await learnRefresh();render();});
  }else if(action==='source-resume'){
    state.resumeSourceJob29=b.dataset.job;notify('Повторно выберите тот же исходный файл или ссылку в форме импорта. Сохранённые ответы страниц будут использованы без повторной отправки.');
  }else if(action==='local-source'){
    const f=b.closest('form'),v=Object.fromEntries(new FormData(f));
    perform(async()=>{const selected=await rpc('pick_source',{student:v.student});if(!selected)return;await import29(v,selected.handle);});
  } else if(action==='method-skills'){
    perform(async()=>{const result=await learnCall('method_skills',{student:state.selected,book:b.dataset.book,method:b.dataset.method});
      const f=document.querySelector('[data-learning-form="curriculum"]');if(!f)return;
      state.importCandidate=result.candidate;
      const panel=document.createElement('section');panel.className='card';panel.innerHTML='<h3>Предпросмотр навыков соответствующего УМК</h3><pre>'+esc(JSON.stringify(result.candidate.topics,null,2))+'</pre><button type="button" data-uf29="apply-method">Явно заменить редактируемый кандидат</button>';f.before(panel);
    });
  } else if(action==='apply-method'){
    const f=document.querySelector('[data-learning-form="curriculum"]'),candidate=state.importCandidate;if(!f||!candidate)return;
    f.elements.title.value=candidate.title||'';f.elements.topics.value=candidate.topics.map(t=>t.title+' | '+t.skills.join('; ')).join('\n');saveLearningDraft(f);f.closest('details').open=true;f.elements.topics.focus();
  } else if(['diagnose','topic-homework','study'].includes(action)){
    selectLearningSubject(b.dataset.subject);state.learnTopic=b.dataset.topic;
    if(action==='diagnose'){navigate('learning');notify('Тема выбрана. Выберите утверждённую подборку в диагностике.');}
    else if(action==='topic-homework'){navigate('homework');}
    else perform(async()=>{const r=await learnCall('study_topic',{student:state.selected,subject:b.dataset.subject,topic:b.dataset.topic});notify('Объяснение готовится. Результат — в задачах учебного процесса.');navigate('learning');await learnRefresh();render();});
  }
});
async function import29(v,handle=null){
  const args={student:v.student,subject:v.subject,kind:v.kind};
  if(state.resumeSourceJob29)args.resume_job=state.resumeSourceJob29;
  if(handle)args.handle=handle;else args.url=v.url;
  if(v.pages.trim())args.pages=v.pages.split(',').map(s=>Number(s.trim())-1);
  const job=await learnCall('import_source',args);state.resumeSourceJob29=null;notify('Импорт запущен. Полный PDF не сохраняется; обновите состояние задач.');await learnRefresh();render();return job;
}
document.addEventListener('submit',e=>{const f=e.target.closest('[data-uf29]');if(!f)return;e.preventDefault();const v=Object.fromEntries(new FormData(f));
  if(f.dataset.uf29==='import')perform(()=>import29(v));
  else if(f.dataset.uf29==='match')perform(async()=>{const match=await learnCall('match_sources',v);await learnRefresh();render();notify(match.status==='compatible'?'УМК соответствует по проверенным реквизитам и адресации. Можно перенести навыки.':match.reasons.join('; '));});
});
// Keep candidate metadata when transferring into the manual alternative editor.
document.addEventListener('click',e=>{const b=e.target.closest('[data-learning="use-candidate"]');if(!b)return;
  const result=learnData()?.jobs.find(j=>j.id===b.dataset.job)?.body.result,candidate=result?.candidate;
  const form=document.querySelector('[data-learning-form="curriculum"]');
  if(!candidate||!form)return;
  const sid=state.learnSubject??Object.keys(subjects)[0];
  if(result.base_revision!==undefined&&result.base_revision!==learnData().states[sid].revision){e.stopImmediatePropagation();notify('Назначение изменилось после импорта. Подготовьте кандидат для актуального издания.');return;}
  const draft=form.elements.topics.value.trim();
  if(draft&&!state.candidateReplaceApproved){e.stopImmediatePropagation();notify('Сохранён ручной черновик. Повторите перенос, чтобы явно заменить его кандидатом.');state.candidateReplaceApproved=true;return;}
  state.importCandidate=candidate;state.candidateReplaceApproved=false;
  const assignment=document.querySelector('[data-learning-form="assignment"]');
  if(assignment&&!state.learningDrafts?.[learningDraftKey(assignment)]){for(const name of ['title','authors','publisher','year','edition'])if(candidate[name]&&assignment.elements[name])assignment.elements[name].value=Array.isArray(candidate[name])?candidate[name].join(', '):candidate[name];saveLearningDraft(assignment);}
},true);
document.addEventListener('submit',e=>{const f=e.target.closest('[data-learning-form="curriculum"]');if(!f||!state.importCandidate)return;
  // Existing form handler performs validation. Attach matching provenance to each
  // leaf in the RPC below; manual title/skill edits become manual provenance.
  state.pendingCandidate=state.importCandidate;
},true);
const originalLearnCall29=learnCall;
learnCall=async function(action,args={}){
  if(action==='curriculum'&&state.pendingCandidate){args.topics=args.topics.map(t=>({...state.pendingCandidate.topics.find(c=>c.title===t.title),...t}));state.pendingCandidate=null;}
  return originalLearnCall29(action,args);
};
const originalAugment29=augmentLearningUI;
augmentLearningUI=function(){originalAugment29();
  const topic=document.querySelector('[data-learning-form="start"] select[name="topic"]');if(topic&&state.learnTopic)topic.value=state.learnTopic;
  const generation=document.querySelector('[data-learning-form="generate"]');if(generation){const p=document.createElement('p');const ctx=learnData()?.contexts?.[state.learnSubject??Object.keys(subjects)[0]];const n=ctx?.topics.length||0;p.textContent=`Подготовка: ${Math.ceil(n/2)+(n>2?1:0)} партий и отдельный ИИ-review каждой. Каждая тема: 8+2 и резерв. При дополнении повторяется только неудачная партия; число повторов выбирается явно.`;generation.prepend(p);generation.elements.count.value=Math.min(300,Number(generation.elements.count.value));const label=document.createElement('label');label.textContent='Дополнительные попытки для проблемной партии (могут быть платными)';label.innerHTML+='<select name="max_repairs"><option value="0">0 — остановить при ошибке</option><option value="1">Разрешаю максимум 1</option><option value="2">Разрешаю максимум 2</option></select>';generation.querySelector('button').before(label);}
};
knowledge=function(){
 const d=learnData(),sid=state.learnSubject??Object.keys(subjects)[0];
 if(!d)return '<h1>Карта знаний</h1><button data-learning="refresh">Загрузить программу и карту</button>';
 const ctx=d.contexts[sid];return `<h1>Карта знаний</h1>${learningSubjectPicker()}<p>Доступность, прохождение и подтверждение освоения учитываются отдельно.</p>${ctx.topics.map(t=>`<article class="card"><small>${esc(t.outline.chapter||'')} · ${esc(t.outline.paragraph||'')}</small><h2>${esc(t.title)}</h2><p>${t.opened?'Открыта для точечного теста':'Будущая тема'} · ${t.studied_requested?'Прохождение ожидает решения · ':''}${t.studied_approved?'Прохождение утверждено':'Прохождение не утверждено'} · ${t.knowledge_confirmation?'Освоение подтверждено':'Освоение не подтверждено'}</p></article>`).join('')||'<p>Пока нет опубликованной программы.</p>'}<button data-action="route" data-value="history">Архив занятий и прежних оценок</button>`;
};
