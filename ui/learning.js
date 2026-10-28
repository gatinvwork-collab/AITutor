'use strict';
const learningLabels={pending:'Ожидает решения',approved:'Одобрено',rejected:'Отклонено',pending_parent:'Ожидает родителя',running:'Выполняется',succeeded:'Готово',failed:'Ошибка',stale:'Устарело',cancelled:'Отменено',active:'Активна',paused:'Приостановлена',completed:'Завершена',C:'Проверено верно',W:'Проверенная ошибка',U:'Не проверено',S:'Ответ не принят'};
Object.assign(learningLabels,{resolved:'Рассмотрен',revoked:'Контроль возобновлён',verified:'Проверено',partially_verified:'Проверено частично',incomplete:'Не завершено'});
function augmentLearningUI(){
  const f=document.querySelector('form[data-form="provider"]');
  if(f&&!f.elements.allow_images){const label=document.createElement('label');label.className='check';const box=document.createElement('input');box.type='checkbox';box.name='allow_images';box.checked=state.data.provider.allow_images===true;label.append(box,document.createTextNode('Отдельно разрешаю передачу фотографий для OCR через GigaChat'));f.querySelector('button').before(label);}
  const current=learnData();
  document.querySelectorAll('form[data-learning-form="decide"]').forEach(form=>{
    const request=current?.requests.find(r=>r.id===form.elements.request.value);
    if(request?.kind==='answer_review'){form.replaceWith(Object.assign(document.createElement('p'),{textContent:'Для этого запроса проверьте исходный ответ в карточке диагностической попытки ниже.'}));}
    else if(request?.kind==='exclusion'){const label=document.createElement('label');label.textContent='Изменить дату окончания (необязательно)';const input=document.createElement('input');input.type='datetime-local';input.name='until';label.append(input);form.querySelector('button').before(label);}
  });
  if(current&&['knowledge','history'].includes(state.route)){const p=document.createElement('p');p.innerHTML='<button data-action="route" data-value="learning">Новая карта программы, диагностики и журнал работ</button>';document.querySelector('.content').prepend(p);}
  document.querySelectorAll('form[data-learning-form="work_revision"]').forEach(form=>{
    const work=form.elements.work.value,row=learnData()?.works.filter(w=>w.work===work).at(-1);
    const preview=document.createElement('div');
    for(const original of row?.body.originals||[]){const button=document.createElement('button');button.type='button';button.dataset.learning='preview';button.dataset.id=work;button.dataset.original=original;button.textContent='Посмотреть оригинал';preview.append(button);const known=state.learningPreviews?.[original];if(known){const image=document.createElement('img');image.src=known.image;image.alt=known.filename;image.style.maxWidth='100%';image.style.display='block';preview.append(image);}}
    form.before(preview);
    if(row?.body.subject==='informatics'){const button=document.createElement('button');button.type='button';button.dataset.learning='analyze';button.dataset.id=work;button.textContent='Проверить синтаксис Python';form.after(button);}
    if(row){
      const copy=document.createElement('form');copy.dataset.learningForm='work_copy';
      copy.innerHTML=learnHidden('work',work)+learnHidden('expected_revision',row.revision)+learnSubject('subject',row.body.subject)+'<p>Создать новую работу с правильным предметом. Исходник и его проверки сохранятся; копию нужно подтвердить и проверить заново.</p><button>Создать исправленную копию</button>';
      form.closest('details').append(copy);
    }
  });
}
function learnData(){return state.learning?.student===state.selected?state.learning:null;}
function learningSubjectPicker(){
  const selected=state.learnSubject===undefined?Object.keys(subjects)[0]:state.learnSubject;
  return `<label>Предмет<select id="learn-subject"><option value="" ${!subjects[selected]?'selected':''}>Выберите предмет</option>${Object.entries(subjects).map(([k,v])=>`<option value="${k}" ${k===selected?'selected':''}>${esc(v)}</option>`).join('')}</select></label>`;
}
function selectLearningSubject(value){
  state.learnSubject=Object.hasOwn(subjects,value)?value:'';
  state.hwSubject=state.learnSubject||null;state.hwTopic=null;
  if(!state.learnSubject)notify('Выберите доступный предмет.');
}
function learningDraftKey(form){return [state.selected,state.learnSubject??Object.keys(subjects)[0],form.dataset.learningForm,...['work','attempt','slot','request'].map(k=>form.elements[k]?.value||'')].join(':');}
function saveLearningDraft(form){
  const fields={};
  for(const control of form.elements)if(control.name&&control.type!=='hidden'&&control.tagName!=='BUTTON'){
    if(control.type==='checkbox'){(fields[control.name]??=[]).push({value:control.value,checked:control.checked});}
    else fields[control.name]=control.value;
  }
  (state.learningDrafts??={})[learningDraftKey(form)]={fields,revision:form.elements.expected_revision?.value};
}
function restoreLearningDrafts(){
  document.querySelectorAll('[data-learning-form]').forEach(form=>{
    const key=learningDraftKey(form),draft=state.learningDrafts?.[key];if(!draft)return;
    for(const control of form.elements){const saved=draft.fields[control.name];if(saved===undefined)continue;
      if(control.type==='checkbox')control.checked=saved.find(x=>x.value===control.value)?.checked||false;
      else if(control.type!=='hidden'&&control.tagName!=='BUTTON')control.value=saved;
    }
    if(draft.revision!==undefined&&form.elements.expected_revision)form.elements.expected_revision.value=draft.revision;
    const discard=document.createElement('button');discard.type='button';discard.dataset.learning='discard_draft';discard.dataset.draft=key;discard.textContent='Сбросить сохранённый черновик';form.append(discard);
  });
}
function requestSummary(r,d){
  const p=r.body;
  if(r.kind==='assignment')return `<p>${esc(p.fields.title)} · ${esc(p.fields.authors)} · ${esc(p.fields.publisher)}</p><p>${p.replace?'Замена издания':'Исправление реквизитов'}</p>`;
  if(r.kind==='curriculum')return `<h4>${esc(p.title)}</h4><p>Источник: ${esc(p.source||'Ручное составление без внешнего источника')}</p><p>${p.complete?'Автор кандидата отметил полноту':'Полнота не подтверждена'}</p><ol>${p.topics.map(t=>`<li>${esc(t.title)}: ${t.skills.map(esc).join('; ')}</li>`).join('')}</ol>`;
  if(r.kind==='studied')return `<p>Пройденные темы: ${p.topics.map(id=>esc(d.curricula.flatMap(c=>c.topics).find(t=>t.id===id)?.title||'Архивная тема')).join('; ')||'Список очищается'}</p>`;
  if(r.kind==='exclusion')return `<p>${esc(p.reason)}. До ${formatDate(p.until)} (${esc(p.zone)}). Добровольная работа останется доступна.</p>`;
  if(r.kind==='collection')return `<p>Допуск конкретной подборки заданий. Навыков в матрице: ${Object.keys(p.coverage||{}).length}. Перед решением просмотрите вопросы и эталоны в разделе банка.</p>`;
  return '<p>Сохранённый учебный запрос.</p>';
}
function jobSummary(j){
  const r=j.body.result;
  if(r.candidates)return `<p>Найденные источники (проверьте школу и точное издание):</p>${r.candidates.map((c,i)=>`<p>${esc(c.title)}<br><small>${esc(c.url)}</small><button data-learning="select-source" data-job="${j.id}" data-index="${i}">Выбрать для предпросмотра</button></p>`).join('')||'<p>Источник не найден. Укажите ссылку или создайте программу вручную.</p>'}`;
  if(r.candidate)return `<p>${esc(r.candidate.title)} · ${esc(r.source)}</p><p>${(r.candidate.warnings||[]).map(esc).join('; ')}</p><button data-learning="use-candidate" data-job="${j.id}">Перенести в редактируемый предпросмотр</button>`;
  if(r.text)return `<div class="rich-text">${renderRich(r.text)}</div><p>Предложение ИИ. Независимая проверка не выполнена.</p>${r.formal_scope?`<p>${esc(r.formal_scope.message||'Формальный метод не применим к этому формату.')}</p>`:''}`;
  if(r.cleanup_failed)return '<p>Не удалось подтвердить удаление временных файлов на стороне провайдера. Проверьте хранилище GigaChat.</p>';
  return '<p>Результат сохранён. Обновлены связанные данные.</p>';
}
async function learnRefresh(){const id=state.selected,epoch=contextEpoch;if(!id)return;const data=await rpc('learning',{action:'overview',student:id});if(epoch!==contextEpoch||id!==state.selected)throw staleContext();state.learning={...data,student:id};}
async function learnCall(action,args={}){return rpc('learning',{action,...args,operation_id:crypto.randomUUID()});}
const learnHidden=(name,value)=>`<input type="hidden" name="${name}" value="${esc(value)}">`;
function learnSubject(name='subject',value){return `<label>Предмет<select name="${name}">${Object.entries(subjects).map(([k,v])=>`<option value="${k}" ${k===value?'selected':''}>${esc(v)}</option>`).join('')}</select></label>`;}
function learningPage(){
  if(!student())return '<h1>Учебный процесс</h1><p>Добавьте профиль ученика.</p>';
  const d=learnData(),parent=state.data.user.role==='PARENT';
  if(!d)return '<h1>Учебный процесс</h1>'+learningSubjectPicker()+'<button data-learning="refresh">Загрузить программы и работы</button>';
  const sid=state.learnSubject===undefined?Object.keys(subjects)[0]:state.learnSubject;
  if(!Object.hasOwn(subjects,sid)||!d.states[sid])return '<h1>Учебный процесс</h1>'+learningSubjectPicker()+'<p>Выберите доступный предмет перед созданием работы.</p>';
  const s=d.states[sid],c=d.curricula.find(c=>c.id===s.curriculum),topics=c?.topics||[];
  const field=(key,label)=>`<label>${label}<input name="${key}" maxlength="300" value="${esc(s.assignment[key]||'')}" ${key==='title'?'required':''}></label>`;
  const hidden=learnHidden('student',d.student)+learnHidden('subject',sid)+learnHidden('expected_revision',s.revision);
  return `<h1>Учебный процесс</h1><div class="row"><button data-learning="refresh">Обновить состояние</button><span class="badge">${parent?'Решения родителя':'Программа и диагностика'}</span></div>
  <label>Предмет<select id="learn-subject">${Object.entries(subjects).map(([k,v])=>`<option value="${k}" ${k===sid?'selected':''}>${esc(v)}</option>`).join('')}</select></label>
  <div class="callout">Прохождение, оценка системы и подтверждение темы — разные показатели. Предметная диагностика выявляет проблемы; подтверждение возможно только по полной точечной проверке. Старые оценки сохранены отдельно.</div>
  <details class="card"><summary>Учебник: ${esc(s.assignment.title||'не назначен')}</summary><form data-learning-form="assignment">${hidden}${field('title','Название')}${field('authors','Авторы')}${field('publisher','Издательство')}${field('year','Год')}${field('part','Часть')}${field('edition','Издание')}${field('source','Источник')}<label class="check"><input type="checkbox" name="replace">Это замена издания (проверить соответствие тем заново)</label><button>${parent?'Сохранить реквизиты':'Предложить родителю'}</button></form><button data-learning="normalize" data-subject="${sid}" data-revision="${s.revision}">Предложить оформление имени через ИИ</button>${s.normalization?`<p>Предложение: ${esc(s.normalization.suggested_title)}</p>`:''}</details>
  <details class="card"><summary>Источник и программа: ${esc(c?.body.title||'не выбрана')}</summary><form data-learning-form="source">${hidden}<label>HTTPS-ссылка (пусто — поиск по реквизитам)<input name="url" type="url"></label><button>Найти / разобрать источник</button></form><p>Без источника и ИИ доступен ручной путь. Поиск без учебника предлагает федеральную программу; её применимость и полноту подтверждает родитель.</p>
  <form data-learning-form="curriculum">${hidden}<label>Название программы<input name="title" required value="${esc(c?.body.title||'')}"></label><label>Источник<input name="source" value="${esc(c?.body.source||'')}"></label><label>Темы и навыки: одна тема в строке, после | перечислите навыки через ;<textarea name="topics" id="curriculum-${d.student}-${sid}-draft" rows="8" required placeholder='Линейные уравнения | Преобразовать обе части; Проверить корень'></textarea></label><label class="check"><input type="checkbox" name="complete">Состав источника проверен на полноту</label><button>Сохранить кандидат для предпросмотра</button></form></details>
  <section class="card"><h2>Текущая тема и прохождение</h2><form data-learning-form="current">${hidden}<label>Что сейчас изучаете?<select name="topic"><option value="">Не знаю / ещё не изучали</option>${topics.map(t=>`<option value="${t.id}" ${s.current===t.id?'selected':''}>${esc(t.title)}</option>`).join('')}</select></label><button>Сохранить текущую тему</button></form>
  ${topics.length?`<form data-learning-form="studied">${hidden}<h3>Предложить список пройденных тем</h3>${topics.map(t=>`<label class="check"><input name="topics" value="${t.id}" type="checkbox" ${s.studied.includes(t.id)?'checked':''}>${esc(t.title)}</label>`).join('')}<button>Передать на подтверждение</button></form>`:'<p>Опубликуйте программу, чтобы увидеть её темы.</p>'}</section>
  <section class="card"><h2>Карта программы</h2>${d.map.filter(t=>t.subject===sid).map(t=>`<article><h3>${esc(t.title)}</h3><p>${t.studied?'Прохождение подтверждено':'Прохождение не подтверждено'} · ${t.confirmed?'Освоение подтверждено':'Недостаточно доказательств освоения'} · Ошибок: ${t.errors}${t.excluded?' · Контроль временно отключён':''}</p><small>Навыки: ${t.skills.map(x=>esc(x.title)).join('; ')}</small></article>`).join('')||'<p>Нет опубликованной программы. Неизвестный уровень не означает 0%.</p>'}
  ${topics.length?`<form data-learning-form="exclude">${hidden}<label>Тема<select name="topic">${topics.map(t=>`<option value="${t.id}">${esc(t.title)}</option>`).join('')}</select></label><label>Дата и время окончания<input name="until" type="datetime-local" required></label><label>Часовой пояс<input name="zone" value="${esc(Intl.DateTimeFormat().resolvedOptions().timeZone)}" required></label><label>Причина<input name="reason" required maxlength="1000"></label><button>Запросить временное исключение контроля</button></form>`:''}</section>
  <details class="card"><summary>Родительские запросы и предпросмотр</summary>${d.requests.map(r=>`<article><h3>${esc(r.kind)} · ${esc(learningLabels[r.status]||r.status)}</h3>${requestSummary(r,d)}${parent&&r.status==='pending'?`<form data-learning-form="decide">${learnHidden('student',d.student)}${learnHidden('request',r.id)}${learnHidden('expected_revision',r.revision)}<label>Обоснование<input name="reason" required maxlength="2000"></label><label>Решение<select name="accept"><option value="true">Подтвердить</option><option value="false">Отклонить</option></select></label><button>Сохранить решение</button></form>`:''}${parent&&r.kind==='exclusion'&&r.status==='approved'?`<button data-learning="revoke_exclusion" data-id="${r.id}" data-revision="${r.revision}">Досрочно вернуть контроль</button>`:''}</article>`).join('')||'<p>Запросов нет.</p>'}</details>
  <section class="card"><h2>Генерируемый банк</h2><p>Генерация → отдельная ИИ-проверка → проверки структуры и рубрик → решение родителя. Утверждение подборки не является проверкой будущих ответов.</p><form data-learning-form="generate">${hidden}<label>Число вопросов<input name="count" type="number" min="10" max="300" value="${Math.max(40,topics.length*6)}"></label><button>Подготовить подборку и резерв</button></form>
  ${d.collections.map(col=>`<details><summary>${esc(col.id.slice(0,8))} · ${esc(learningLabels[col.status]||col.status)}</summary>${parent?(col.questions||[]).map(q=>`<article>${renderRich(q.body.statement)}<p>${q.starred?'Сложное *':'Обязательное'}</p><h4>Эталон</h4>${q.body.steps.map(renderRich).join('<br>')}<pre>${esc(JSON.stringify(q.criteria,null,2))}</pre></article>`).join(''):'<p>Эталоны скрыты.</p>'}</details>`).join('')||'<p>Подборок нет. Диагностика не будет подменена тремя старыми заданиями.</p>'}
  ${!parent?`<form data-learning-form="start">${hidden}<label>Утверждённая подборка<select name="collection" required>${d.collections.filter(x=>x.status==='approved'&&x.curriculum===s.curriculum).map(x=>`<option value="${x.id}">${esc(x.id.slice(0,8))}</option>`).join('')}</select></label><label>Цель<select name="purpose"><option value="topic_confirmation">Подтверждение темы: 8+2*</option><option value="subject_screening">Скрининг предмета: 27+3*</option></select></label><label>Тема<select name="topic">${topics.map(t=>`<option value="${t.id}">${esc(t.title)}</option>`).join('')}</select></label><button>Создать неизменяемый план и начать</button></form>`:''}</section>
  <h2>Диагностические попытки</h2>${d.attempts.map(a=>attemptCard(a,parent)).join('')||'<p>Новые диагностики ещё не запускались.</p>'}
  <section class="card"><h2>Работа с решением и фотографиями</h2>${!parent?`<form data-learning-form="work">${hidden}<button>Создать работу по ${esc(subjects[sid])}</button></form>`:''}${learningWorks(d,parent)}</section>
  <section class="card"><h2>Фоновые задачи</h2><button data-learning="refresh">Проверить состояние задач</button>${d.jobs.map(j=>`<article><strong>${esc(j.body.kind)}</strong> · ${esc(learningLabels[j.status]||j.status)}${j.body.code?`<p>Причина: ${esc(j.body.code)}. Доступен ручной путь или явный повтор.</p>`:''}${j.body.result?`${jobSummary(j)}`:''}</article>`).join('')||'<p>Задач нет.</p>'}</section>`;
}
function attemptCard(a,parent){
  const r=a.result,hidden=learnHidden('attempt',a.id)+learnHidden('expected_revision',a.revision);
  return `<details class="card"><summary>${esc(a.purpose==='topic_confirmation'?'Подтверждение темы':'Скрининг предмета')} · ${esc(learningLabels[a.status])} · ${formatDate(a.body.created)}</summary><p>C=${r.C} · W=${r.W} · U=${r.U} · S=${r.S} · P=${r.P===null?'—':r.P.toFixed(2)+'%'} · K=${r.K===null?'—':r.K.toFixed(2)+'%'}</p><p>${r.confirmed?'Освоение подтверждено':'Подтверждение освоения не выдано'} · ${esc(r.verification)}</p>
  ${a.slots.map(slot=>`<article><h3>Вопрос ${slot.position+1}${slot.starred?' *':''}</h3><div class="rich-text">${renderRich(slot.statement)}</div>${slot.answers.map(ans=>`<div><small>Ответ ${ans.revision}${ans.independent?' · исходный самостоятельный':''}</small>${renderRich(ans.body.text)}</div>`).join('')}
  ${!parent&&a.status==='active'?`<form data-learning-form="submit">${hidden}${learnHidden('slot',slot.id)}<label>Ответ и необходимые шаги<textarea name="answer" required rows="4" data-text-limit="30000"></textarea></label><button>Сохранить ответ</button></form>${slot.starred?`<form data-learning-form="skip">${hidden}${learnHidden('slot',slot.id)}<button>Явно пропустить *</button></form>`:''}`:''}
  ${slot.components.map(component=>`<p>${esc(learningLabels[component.code])}${component.observation?` · ${esc(component.observation.method)} · ${esc(JSON.parse(component.observation.body).reason||'')}`:''}</p>${parent&&component.answer?`<form data-learning-form="review">${learnHidden('attempt',a.id)}${learnHidden('answer',component.answer)}${learnHidden('criterion',component.criterion)}${learnHidden('expected_revision',component.observation?.revision||0)}<label>Область проверки<input name="scope" required value="${esc(slot.reference?.criteria.find(c=>c.id===component.criterion)?.body.criterion||'')}"></label><label>Вердикт<select name="code"><option value="C">Проверено верно</option><option value="W">Проверенная ошибка</option><option value="U">Не удалось проверить</option></select></label><label>Обоснование<input name="reason" required maxlength="2000"></label><button>Проверить именно исходный ответ</button></form>`:''}`).join('')}
  ${slot.answers[0]?`<button data-learning="retry" data-attempt="${a.id}" data-answer="${slot.answers[0].id}">Получить ИИ-анализ исходного ответа</button>`:''}</article>`).join('')}
  ${!parent&&a.status!=='completed'?`<form data-learning-form="${a.status==='paused'?'resume':'pause'}">${hidden}<button>${a.status==='paused'?'Продолжить':'Сохранить и приостановить'}</button></form><form data-learning-form="finish">${hidden}<button>Завершить попытку</button></form>`:''}<p>Unknown разрешается перепроверкой того же ответа. Новое задание не заменяет вопрос и N исходной попытки.</p></details>`;
}
function learningWorks(d,parent){
  const latest=new Map();for(const r of d.works)latest.set(r.work,r);
  return [...latest.values()].map(w=>`<details open><summary>Работа ${esc(w.work.slice(0,8))} · версия ${w.revision} · ${w.body.confirmed?'Текст подтверждён':'Проверьте распознавание'}</summary><p>Оригиналов: ${w.body.originals.length}. Старые версии сохранены.</p>${!parent?`<form data-learning-form="work_revision">${learnHidden('work',w.work)}${learnHidden('expected_revision',w.revision)}<label>Условие и решение (TeX: $...$)<textarea name="value" rows="7" data-text-limit="30000" required>${esc(state.drafts['work-'+w.work]??w.body.text)}</textarea></label><label class="check"><input name="confirm" type="checkbox" ${w.body.confirmed?'checked':''}>Я проверил текст и формулы по оригиналам</label><button>Сохранить новую версию</button></form><div class="row"><button data-learning="work_original" data-id="${w.work}" data-revision="${w.revision}">Прикрепить ещё фото/файл</button><button data-learning="recognize" data-id="${w.work}" data-revision="${w.revision}">Распознать фото через GigaChat</button></div><form data-learning-form="work_check">${learnHidden('work',w.work)}${learnHidden('expected_revision',w.revision)}<label>Действие<select name="intent"><option value="check">Проверить полное решение</option><option value="hint">Дать подсказку</option><option value="follow_up">Продолжить диалог</option></select></label><label>Уточнение<textarea name="follow_up" rows="2"></textarea></label><button>Отправить эту версию</button></form>`:''}<div class="rich-text">${renderRich(w.body.text)}</div>${d.calls.filter(c=>c.work===w.work).map(c=>`<article class="message">${renderRich(c.body.response)}<p class="muted">Метод: ИИ; независимая проверка не выполнена. ${esc(c.body.model)}</p><details><summary>Фактически переданный учебный контекст</summary><pre>${esc(JSON.stringify(c.body.messages,null,2))}</pre></details></article>`).join('')}</details>`).join('');
}
document.addEventListener('change',e=>{if(e.target.id==='learn-subject'){selectLearningSubject(e.target.value);render();}});
document.addEventListener('input',e=>{const form=e.target.closest('[data-learning-form]');if(form)saveLearningDraft(form);const f=e.target.closest('[data-learning-form="work_revision"]');if(f&&e.target.name==='value')state.drafts['work-'+f.elements.work.value]=e.target.value;});
document.addEventListener('change',e=>{const form=e.target.closest('[data-learning-form]');if(form)saveLearningDraft(form);});
document.addEventListener('click',e=>{
  const b=e.target.closest('[data-learning]');if(!b||b.disabled||inFlight)return;
  perform(async()=>{const a=b.dataset.learning;if(a==='refresh'){await learnRefresh();render();return;}
    if(a==='select-source'){const result=learnData().jobs.find(j=>j.id===b.dataset.job).body.result;const input=document.querySelector('[data-learning-form="source"] input[name="url"]');input.value=result.candidates[Number(b.dataset.index)].url;input.closest('details').open=true;input.focus();return;}
    if(a==='use-candidate'){const result=learnData().jobs.find(j=>j.id===b.dataset.job).body.result;const form=document.querySelector('[data-learning-form="curriculum"]');form.elements.title.value=result.candidate.title||'';form.elements.source.value=result.source;form.elements.topics.value=(result.candidate.topics||[]).map(t=>t.title+' | '+t.skills.join('; ')).join('\n');form.closest('details').open=true;form.elements.topics.focus();return;}
    if(a==='discard_draft'){
      const form=b.closest('form');
      if(form?.dataset.learningForm==='work_revision')delete state.drafts['work-'+form.elements.work.value];
      for(const control of form?.elements||[])if(control.id?.endsWith('-draft'))delete state.drafts[control.id];
      delete state.learningDrafts[b.dataset.draft];render();return;
    }
    let result;
    if(a==='normalize')result=await learnCall(a,{student:state.selected,subject:b.dataset.subject,expected_revision:Number(b.dataset.revision)});
    else if(a==='work_original'){const file=await rpc('pick_file');if(!file)return;result=await learnCall(a,{work:b.dataset.id,homework:file.id,expected_revision:Number(b.dataset.revision)});}
    else if(a==='recognize')result=await learnCall(a,{work:b.dataset.id,expected_revision:Number(b.dataset.revision)});
    else if(a==='analyze'){result=await learnCall(a,{work:b.dataset.id});notify(result.text);return;}
    else if(a==='preview'){result=await learnCall(a,{work:b.dataset.id,original:b.dataset.original});(state.learningPreviews??={})[b.dataset.original]=result;render();return;}
    else if(a==='retry')result=await learnCall(a,{attempt:b.dataset.attempt,answer:b.dataset.answer});
    else if(a==='revoke_exclusion')result=await learnCall(a,{student:state.selected,request:b.dataset.id,expected_revision:Number(b.dataset.revision)});
    if(result?.job)notify('Задача запущена. Меню и локальное сохранение доступны; состояние — внизу страницы.');
    await learnRefresh();render();
  });
});
document.addEventListener('submit',e=>{
  const f=e.target.closest('[data-learning-form]');if(!f)return;e.preventDefault();if(inFlight)return;
  const fd=new FormData(f),v=Object.fromEntries(fd),action=f.dataset.learningForm,draftKey=learningDraftKey(f);
  if(v.expected_revision!==undefined)v.expected_revision=Number(v.expected_revision);
  perform(async()=>{
    if(action==='assignment'){v.fields=Object.fromEntries(['title','authors','publisher','year','part','edition','source'].map(k=>[k,v[k]]));for(const k of Object.keys(v.fields))delete v[k];v.replace=fd.has('replace');}
    if(action==='curriculum'){v.topics=v.topics.trim().split(/\r?\n/).filter(x=>x.trim()).map(line=>{const [title,...parts]=line.split('|');const skills=parts.join('|').split(';').map(x=>x.trim()).filter(Boolean);if(!skills.length)throw Error('Укажите навыки каждой темы после |, разделив их знаком ;');return {title:title.trim(),skills};});v.complete=fd.has('complete');}
    if(action==='current')v.topic=v.topic||null;
    if(action==='studied')v.topics=fd.getAll('topics');
    if(action==='decide'){v.accept=v.accept==='true';if(v.until)v.until=new Date(v.until).toISOString();else delete v.until;}
    if(action==='generate')v.count=Number(v.count);
    if(action==='source'){if(!v.url)delete v.url;delete v.expected_revision;}
    if(['generate','work','start'].includes(action))delete v.expected_revision;
    if(action==='start'){delete v.subject;}
    if(action==='exclude'){delete v.expected_revision;v.until=new Date(v.until).toISOString();}
    if(action==='work_revision')v.confirm=fd.has('confirm');
    const result=await learnCall(action,v);
    if(state.learningDrafts)delete state.learningDrafts[draftKey];
    if(action==='curriculum')delete state.drafts[f.elements.topics.id];
    if(action==='work_revision')delete state.drafts['work-'+v.work];
    notify(result?.job?'Фоновая задача запущена. Обновите состояние для просмотра результата.':'Данные сохранены.');
    await refreshLearningState();await learnRefresh();render();
  });
});
