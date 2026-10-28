'use strict';

const $ = s => document.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {route:'home', data:null, status:null, authMode:'login', selected:null, lesson:null, homework:null, drafts:{}};
let bridge, inFlight = 0;
let contextEpoch=0,nativeContext=null,noticeTimer=null,cancelTransition=null;
let navigationRevision=0,currentOperation=null;
const busyControls=new Set();
const pending = new Map();
let subjects = {};
const icons = {algebra:'∑',geometry:'△',physics:'ρ',informatics:'01'};
const roleName = role => ({PARENT:'Родитель',STUDENT:'Ученик'}[role]||'');
function applyAppearance(theme,design) {
  document.body.dataset.colorPreference=theme;
  document.body.dataset.theme=theme==='system'?(window.nativeColorScheme||'system'):theme;
  document.body.dataset.design=design;
}

function staleContext() { return Object.assign(new Error('Контекст доступа изменился.'),{stale:true}); }
function resetPersonalState(context=null) {
  ++contextEpoch;++navigationRevision;nativeContext=context;
  for(const job of pending.values()){clearTimeout(job.timer);job.reject(staleContext());}pending.clear();
  if(cancelTransition)cancelTransition(false);
  for(const key of Object.keys(state))delete state[key];
  Object.assign(state,{route:'home',data:null,status:null,authMode:'login',selected:null,lesson:null,homework:null,drafts:{}});
  subjects={};clearTimeout(noticeTimer);$('#notice').textContent='';$('#notice').classList.remove('show');
  for(const dialog of document.querySelectorAll('dialog')){if(dialog.open)dialog.close();}
  $('#secret-value').textContent='';$('#transition-text').textContent='';
  $('#app').replaceChildren();delete $('#app').dataset.shell;applyAppearance('system','strict');
}
function notify(text) {clearTimeout(noticeTimer);$('#notice').textContent = text; $('#notice').classList.add('show');noticeTimer=setTimeout(() => $('#notice').classList.remove('show'), 7000);}
function rpc(command, args={}) {
  const id = crypto.randomUUID();
  return new Promise((resolve,reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(new Error('Операция длится дольше ожидаемого. Обновите состояние перед повтором.')); }, command==='run_transfer'?1800000:200000);
    pending.set(id,{resolve,reject,timer,epoch:contextEpoch,command});
    bridge.request(id,command,JSON.stringify(args));
  });
}
function syncBusyState() {
  if(!inFlight){for(const control of busyControls)if(control.isConnected)control.disabled=false;busyControls.clear();}
  else for(const control of document.querySelectorAll('button,input,select,textarea')){
    if(control.matches('nav [data-action="route"],#cancel-request,#transition-accept,#transition-cancel,#learn-subject'))continue;
    if(!control.disabled){control.disabled=true;busyControls.add(control);}
  }
  document.querySelector('.content')?.setAttribute('aria-busy',String(!!inFlight));
}
function operationOwnsScreen(){return !currentOperation||(currentOperation.epoch===contextEpoch&&currentOperation.revision===navigationRevision);}
function operationRoute(route){if(operationOwnsScreen())state.route=route;}
function navigate(route) {
  const nav=state.data?.user.role==='PARENT'?parentNav:studentNav;
  if(!state.data||!nav.some(([id])=>id===route)){notify('Этот раздел недоступен текущему профилю.');return;}
  ++navigationRevision;state.route=route;render();
}
async function perform(fn) {
  if(inFlight) return;
  currentOperation={epoch:contextEpoch,revision:navigationRevision,route:state.route};
  inFlight++; $('#busy').hidden=false;
  syncBusyState();
  try { await fn(); } catch(e) { if(!e.stale)notify(e.message); }
  finally { inFlight--;currentOperation=null;$('#busy').hidden=true;syncBusyState(); }
}
async function refresh() {
  state.status=await rpc('status');
  if(!state.status.exists) state.authMode='register';
  if(state.status.authenticated) {
    state.data=await rpc('snapshot');
    subjects=state.data.subjects;
    if(!state.selected || !state.data.students.some(s=>s.id===state.selected)) state.selected=state.data.students[0]?.id;
    applyAppearance(state.data.user.theme,state.data.user.design);
    if(state.lesson) state.lesson=student()?.sessions.find(s=>s.id===state.lesson.id) || null;
    reconcileSnapshot();
  } else {
    const status=state.status;
    resetPersonalState(status.context);state.status=status;
    if(!status.exists)state.authMode='register';
  }
  render();
}
function student(){ return state.data?.students.find(s=>s.id===state.selected); }
async function refreshLearningState() {
  state.data=await rpc('snapshot');subjects=state.data.subjects;
  if(state.lesson)state.lesson=student()?.sessions.find(s=>s.id===state.lesson.id)||null;
  reconcileSnapshot();
}
function reconcileSnapshot() {
  if(!state.data)return;
  const parent=state.data.user.role==='PARENT';
  state.report=parent&&state.report?.id?(student()?.sessions.find(s=>s.id===state.report.id)||null):null;
  if(state.profileEdit&&!state.data.editable_profiles.some(p=>p.id===state.profileEdit.id)){
    state.profileEdit=null;state.profileDirty=false;if(state.route==='profile')state.route='settings';
  }
  if(state.lesson&&(parent||state.lesson.student!==state.data.user.id))state.lesson=null;
}
function askPause(title) {
  const dialog=$('#transition');$('#transition-text').textContent=`Сейчас открыто «${title}». Перед началом другой работы его нужно сохранить и приостановить. Прогресс останется в истории.`;
  $('#transition-accept').disabled=false;$('#transition-cancel').disabled=false;
  dialog.showModal();
  return new Promise(resolve=>{
    const finish=accepted=>{dialog.close();dialog.oncancel=null;cancelTransition=null;resolve(accepted);};
    cancelTransition=finish;
    $('#transition-accept').onclick=()=>finish(true);$('#transition-cancel').onclick=()=>finish(false);
    dialog.oncancel=event=>{event.preventDefault();finish(false);};
  });
}
function formatDate(value) { return value ? new Date(value).toLocaleString('ru-RU') : '—'; }
function subjectDisplay(item) {
  if(item.subject==='math')return 'Математика — архив'+(subjects[item.catalog_subject]?' · '+subjects[item.catalog_subject]:'');
  return item.subject_label||subjects[item.subject]||'Предмет не определён';
}
function subjectFilter(id,value,archive=false) {
  const kind=id==='history-subject'?'history':'knowledge';
  const entries={...subjects,...(archive?(student()?.archives?.[kind]||{}):{})};
  return `<label>Предмет<select id="${id}"><option value="">Все предметы</option>${Object.entries(entries).map(([key,label])=>`<option value="${key}" ${value===key?'selected':''}>${esc(label)}</option>`).join('')}</select></label>`;
}
function minutes(seconds){ return Math.round((seconds||0)/60); }
function validateTextLimit(field) {
  const limit=Number(field.dataset.textLimit);let length=0;
  for(const character of field.value){if(++length>limit)break;}
  field.setCustomValidity(length>limit?'Текст превышает 30 000 символов. Разбейте задание на части.':'');
}
function showSecrets(result) {
  $('#secret-value').textContent=`Идентификатор входа:\n${result.id || state.data?.user.id || ''}\n\n${result.recovery_key ? 'Ключ восстановления:\n'+result.recovery_key : ''}`;
  $('#secret').showModal();
}
$('#secret-close').addEventListener('click',()=>{$('#secret-value').textContent='';$('#secret').close();});
$('#cancel-request').addEventListener('click',async()=>{await rpc('cancel_request');notify('Запрошена отмена операции. Дождитесь завершения текущего шага.');});

function auth() {
  if(state.status?.transfer_pending)return `<main class="welcome"><section class="card"><h1>Незавершённый перенос</h1><p>Регистрация и вход приостановлены. Проверьте ранее опубликованную копию или удалите только временные файлы этой операции. Исходная установка сохранена.</p><button data-action="recover-transfer">Завершить проверку / очистить временную копию</button></section></main>`;
  const register=state.authMode==='register';
  const recover=state.authMode==='recover';
  return `<main class="welcome"><header>${brand()}<span class="badge">Локальное обучение · 7 класс</span><h1>Учиться. Понимать. Продвигаться.</h1><p class="muted">Алгебра, геометрия, физика и информатика.<br>Учебная история хранится на вашем компьютере в зашифрованном виде.</p></header>
  <section class="card auth"><h2>${register?'Создать первый профиль':recover?'Восстановить доступ':'Войти в профиль'}</h2>
  ${!state.status?.exists?'<p class="muted">Начните с профиля родителя или ученика. Для ИИ-занятий потребуется родитель.</p>':''}
  <form data-form="${register?'register':recover?'recover':'login'}">
    ${register?registerFields():`<label>Профиль<select name="account" required>${accountOptions()}</select></label><small>Имя и роль доступны до входа. Остальные данные открываются после ввода пароля.</small>`}
    ${recover?'<label>Ключ восстановления<input name="recovery_key" type="password" required autocomplete="off"></label><label>Новый пароль<input name="new_password" type="password" minlength="10" required autocomplete="new-password"></label>':register?'':'<label>Пароль<input name="password" type="password" required autocomplete="current-password"></label>'}
    <button class="primary" type="submit">${register?'Создать профиль':recover?'Восстановить':'Войти'}</button>
  </form><hr class="divider"><div class="row">${state.status?.exists?`<button data-action="auth" data-value="${recover?'login':'recover'}">${recover?'Вернуться ко входу':'Забыли пароль?'}</button>`:`<button data-action="auth" data-value="register">Первый запуск → создать профиль</button>`}</div></section>
  ${!state.status?.exists?transferCard():''}
  <p class="muted">Tutor-AI · Версия 0.5.0a4 · Рабочий прототип. Полная приёмка MVP ещё не пройдена.</p></main>`;
}
function transferCard(){
  const plan=state.transferPlan;
  if(state.transferDone)return `<section class="card"><h2>Перенос завершён</h2><p>Источник сохранён. Новая установка: ${esc(state.transferDone.destination)}</p><button data-action="launch-transfer">Запустить новую установку</button></section>`;
  return `<section class="card"><h2>Перенести данные из прежней версии</h2><p>Закройте прежнее приложение. Выберите корень установки с папкой app-data. История, вложения и резервные копии будут проверены и скопированы; источник сохранится.</p><label class="check"><input id="transfer-separate" type="checkbox">Создать Portable-комплект в другой пустой папке (из exe)</label><button data-action="choose-transfer">Выбрать папки</button><button data-action="choose-transfer-recovery">Очистить незавершённый перенос в другой папке</button>${plan?`<p>Источник: ${esc(plan.source)}<br>Назначение: ${esc(plan.destination)}<br>Файлов: ${plan.files}</p><form data-form="transfer"><label>Существующий профиль<select name="account" required>${plan.accounts.map(a=>`<option value="${esc(a.id)}">${esc(a.name||a.id)} ${esc(roleName(a.role))}</option>`).join('')}</select></label><label>Прежний пароль<input name="password" type="password" required autocomplete="off"></label><label class="check"><input type="checkbox" required>Подтверждаю перенос в указанную папку</label><button class="primary">Проверить и перенести</button></form><button data-action="recover-transfer">Очистить незавершённую копию после ошибки</button>`:''}</section>`;
}
function accountOptions() {
  const accounts=state.status?.accounts||[];
  return accounts.map(a=>{
    const duplicate=accounts.filter(other=>other.name===a.name&&other.role===a.role).length>1;
    const label=a.name?`${a.name} · ${roleName(a.role)}${duplicate?' · '+a.id.slice(0,8):''}`:`Профиль ${a.id.slice(0,8)}… (имя появится после первого входа)`;
    return `<option value="${esc(a.id)}">${esc(label)}</option>`;
  }).join('');
}
function registerFields() {
  return `<label>Роль<select name="role"><option value="PARENT">Родитель</option><option value="STUDENT">Ученик</option></select></label><label>Имя<input name="name" maxlength="60" required autocomplete="off"></label><label>Пароль (не менее 10 символов)<input name="password" type="password" minlength="10" required autocomplete="new-password"></label><p class="muted">Имя и роль будут видны в списке входа. Для ученика заполните данные школы; полное ФИО не требуется.</p>${addressFields()}<label>Школа (ручной ввод)<input name="school" maxlength="200"></label><label>Класс<input value="7" readonly></label>`;
}
const studentNav=[['home','Обзор'],['subjects','Предметы'],['lesson','Текущее занятие'],['homework','Проверка ДЗ'],['learning','Учебный процесс'],['knowledge','Карта знаний'],['history','История'],['program','Учебник и программа'],['settings','Настройки']];
const parentNav=[['home','Обзор семьи'],['students','Профили и связи'],['notifications','Уведомления'],['learning','Учебный процесс'],['knowledge','Карта знаний'],['history','Занятия и отчёты'],['controls','Учебное время'],['program','Программы и запросы'],['providers','ИИ-провайдеры'],['backup','Резервные копии'],['security','Безопасность'],['settings','Настройки']];
function brand(){return '<div class="brand-lockup"><img src="assets/tutor-ai-mark.svg" width="48" height="48" alt=""><div><span class="brand-wordmark">Tutor<span>-AI</span></span><small>ИИ-репетитор</small></div></div>';}
function render() {
  const started=performance.now();
  if(!state.data) { $('#app').innerHTML=auth();syncBusyState();return; }
  reconcileSnapshot();
  applyAppearance(state.data.user.theme,state.data.user.design);
  const parent=state.data.user.role==='PARENT';
  const nav=parent?parentNav:studentNav;
  const pages={home,subjects:subjectPage,lesson:lessonPage,homework:homeworkPage,learning:learningPage,knowledge,history,students:studentsPage,controls,program,providers,backup,security,settings,profile:profilePage,notifications:notificationsPage};
  if(!pages[state.route]){
    state.route='home';notify('Недоступный раздел. Открыт обзор текущего профиля.');
  }
  const s=student();
  for(const [key,kind] of [['reportSubject','history'],['knowledgeSubject','knowledge']]) {
    if(state[key]&&!subjects[state[key]]&&!s?.archives?.[kind]?.[state[key]])state[key]='';
  }
  const shellKey=`${contextEpoch}:${state.data.user.id}:${state.data.user.role}`;
  const sameShell=$('#app').dataset.shell===shellKey&&!!$('.sidebar');
  const focused=sameShell?document.activeElement:null;
  const focusId=focused?.id;
  const focusForm=focused?.closest('form')?.dataset.form,focusName=focused?.name;
  const start=focused?.selectionStart,end=focused?.selectionEnd;
  if(!sameShell){
    $('#app').innerHTML=`<div class="layout"><aside class="sidebar"><div class="brand">${brand()}<small>ПОНЯТНО. ПО ШАГАМ.</small></div><nav aria-label="Разделы приложения">${nav.map(([id,label])=>`<button data-action="route" data-value="${id}">${label}</button>`).join('')}</nav><div class="profile"><strong></strong><small>${parent?'Кабинет родителя':'Ученик · 7 класс'}</small><button data-action="logout">Выйти и заблокировать</button></div></aside><main class="content"></main></div>`;
    $('#app').dataset.shell=shellKey;
  }
  $('.profile strong').textContent=state.data.user.name;
  const activeRoute=state.route==='profile'?(state.profileReturn||(parent?'students':'settings')):
    nav.some(([id])=>id===state.route)?state.route:'home';
  const unread=parent?state.data.notifications.filter(n=>!n.read_at).length:0;
  for(const [id,label] of nav){
    const button=$(`nav [data-value="${id}"]`);
    button.classList.toggle('active',id===activeRoute);
    if(id===activeRoute)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
    button.textContent=label+(id==='notifications'&&unread?' · '+unread:'');
  }
  $('.content').innerHTML=`<div class="topline"><span>Ваше пространство обучения</span><span class="badge">Локальная история · v0.5.0a4</span></div>${parent&&state.data.students.length?`<label>Ученик<select id="selected-student">${state.data.students.map(c=>`<option value="${esc(c.id)}" ${c.id===s?.id?'selected':''}>${esc(c.name)}</option>`).join('')}</select></label>`:''}${pages[state.route]()}`;
  const messages=$('.messages'); if(messages) messages.scrollTop=messages.scrollHeight;
  const edit=$('form[data-form="profile"]');
  if(edit&&state.profileEdit?.role==='STUDENT')fillAddress(edit,state.profileEdit.profile);
  for(const [key,value] of Object.entries(state.drafts)) { const input=document.getElementById(key); if(input) input.value=value; }
  document.querySelectorAll('[data-text-limit]').forEach(validateTextLimit);
  augmentLearningUI();restoreLearningDrafts();
  syncBusyState();
  if(focused&&!focused.isConnected){
    const target=focusId?document.getElementById(focusId):focusForm&&focusName?document.querySelector(`form[data-form="${CSS.escape(focusForm)}"] [name="${CSS.escape(focusName)}"]`):null;
    if(target&&!target.disabled){target.focus({preventScroll:true});if(typeof start==='number'&&typeof target.setSelectionRange==='function')try{target.setSelectionRange(start,end);}catch{}}
  }
  if(state.status?.diagnostics){
    const epoch=contextEpoch,revision=navigationRevision,route=state.route,render_ms=performance.now()-started;
    requestAnimationFrame(()=>requestAnimationFrame(()=>{
      if(epoch===contextEpoch&&revision===navigationRevision)rpc('diagnostic_navigation',{
        route,render_ms,raf_ms:performance.now()-started,width:innerWidth,height:innerHeight,dpr:devicePixelRatio
      }).catch(()=>{});
    }));
  }
}
function home() {
  const parent=state.data.user.role==='PARENT',s=student();
  if(!s) return `<h1>Начнём с ученика</h1><section class="hero"><h2>Всё обучение — в одном месте</h2><p>Создайте профиль ребёнка, затем настройте ИИ-провайдера и разрешения на передачу данных.</p><button class="primary" data-action="route" data-value="students">Добавить ученика</button></section>`;
  const k=s.knowledge, mastery=k.length?Math.round(k.reduce((n,t)=>n+t.mastery_score,0)/k.length):null;
  const recommendation=[...k].sort((a,b)=>a.mastery_score-b.mastery_score)[0];
  return `<h1>${parent?`Обучение: ${esc(s.name)}`:`Привет, ${esc(s.name)}!`}</h1><p class="muted">Каждая понятная тема — ещё один шаг вперёд.</p>
  ${!parent&&!state.data.has_parent?'<div class="callout">Пока родитель не подключён, ИИ-занятия недоступны. Откройте настройки и создайте профиль первого родителя.</div>':''}
  <div class="grid"><section class="card"><small>Активное время сегодня</small><div class="stat">${minutes(s.daily.seconds)} <small>мин</small></div><span class="muted">Лимит: ${s.controls.minutes} мин</span></section><section class="card"><small>Завершённых занятий</small><div class="stat">${s.sessions.filter(x=>x.status==='complete').length}</div><span class="muted">История сохраняется локально</span></section><section class="card"><small>Оценка освоения</small><div class="stat">${mastery===null?'—':mastery+'%'}</div><span class="muted">Оценка системы, не школьная отметка</span></section></div>
  <section class="hero"><span class="badge">${recommendation?'Рекомендуем повторить':'Начните с небольшой темы'}</span><h2>${recommendation?esc(state.data.catalog.find(t=>t.id===recommendation.topic)?.title):'Понимание начинается с вопроса'}</h2><p>Разбирайте материал по шагам, пробуйте самостоятельно и обращайтесь к подсказкам, если нужна помощь.</p><button class="primary" data-action="route" data-value="${parent?'knowledge':'subjects'}">${parent?'Посмотреть карту знаний':'Выбрать тему'}</button></section>
  <h2>Четыре предмета — один репетитор</h2>${subjectCards()}`;
}
function subjectCards() {return `<div class="grid">${Object.entries(subjects).map(([id,name])=>`<section class="card"><div class="subject-icon">${icons[id]}</div><h2>${name}</h2><p>Объяснение, практика и обратная связь.</p><button data-action="subject" data-value="${id}">Открыть темы →</button></section>`).join('')}</div>`;}
function subjectPage() {
  const switcher=`<nav class="subject-switcher row" aria-label="Выбор предмета">${Object.entries(subjects).map(([id,name])=>`<button data-action="subject" data-value="${id}" aria-pressed="${id===state.subject}" class="${id===state.subject?'primary':''}">${esc(name)}</button>`).join('')}</nav>`;
  if(!state.subject) return `<h1>Что изучим сегодня?</h1><p class="muted">Выберите предмет и тему.</p>${subjectCards()}`;
  const topics=state.data.catalog.filter(t=>t.subject===state.subject);
  return `${switcher}<h1>${esc(subjects[state.subject])}</h1><button data-action="subject-homework" data-value="${state.subject}">Проверить ДЗ по этому предмету</button>${topics.length?`<button data-action="subject-diagnose" data-value="${topics[0].id}">Диагностика по предмету</button>`:'<p>Каталог тем пока пуст.</p>'}<div class="callout">Это начальный каталог прототипа. Полная программа 7-го класса и привязка к учебникам ещё готовятся.</div><div class="grid">${topics.map(t=>`<section class="card"><h2>${esc(t.title)}</h2><p>${esc(t.theory)}</p><div class="row"><button class="primary" data-action="start" data-value="${t.id}">Изучать</button><button data-action="diagnose" data-value="${t.id}">Диагностика</button></div></section>`).join('')}</div>`;
}
function lessonPage() {
  const l=state.lesson;
  if(!l) return '<h1>Учебное занятие</h1><section class="card empty">Выберите тему в разделе «Предметы» или продолжите сохранённое занятие из истории.</section>';
  if(l.mode==='homework')return `<h1>${esc(l.title)}</h1><span class="badge">${esc(subjects[l.subject]||l.subject_label)} · ДЗ</span><section class="card">${l.messages.map(m=>`<div class="message ${m.role==='user'?'user':''}">${renderRich(m.text)}</div>`).join('')}<div class="row"><button data-action="route" data-value="homework">Открыть проверку ДЗ</button>${l.status==='active'?'<button data-action="pause">Сохранить и приостановить</button><button data-action="complete">Завершить</button>':l.status==='paused'?'<button data-action="resume">Продолжить</button>':''}</div></section>`;
  return `<div class="row spaced"><div><span class="badge">${esc(subjectDisplay(l))} · ${l.mode.includes('diagnose')?'Диагностика':'Изучение'}</span><h1>${esc(l.title)}</h1></div><span class="muted">${l.status==='active'?'Идёт занятие':l.status==='paused'?'Приостановлено':'Завершено'} · ${minutes(l.seconds)} мин</span></div><section class="card"><div class="messages">${l.messages.map(m=>`<div class="message ${m.role==='user'?'user':''}">${renderRich(m.text)}${m.hint?`<p class="muted">Подсказка H${m.hint}</p>`:''}${m.usage?`<p class="muted">Токены: ${esc(JSON.stringify(m.usage))}</p>`:''}</div>`).join('')}</div>
  ${l.status==='active'?`<div class="task"><small>Самостоятельная практика · ${l.index+1} из 3</small><br>${esc(l.task)}</div><form data-form="answer" class="row"><input id="answer-draft" name="answer" placeholder="Твой ответ" required maxlength="500"><button class="primary" type="submit">Проверить</button><button type="button" data-action="hint">Нужна подсказка</button></form><hr class="divider"><form data-form="chat"><label>Что осталось непонятным?<textarea id="question-draft" name="text" maxlength="4000" required placeholder="Задай вопрос по теме…"></textarea></label><div class="row"><button type="submit">Спросить репетитора</button><button type="button" data-action="speak">Озвучить ответ</button></div></form>`:`<div class="callout">${l.status==='complete'?`Занятие завершено. Правильных ответов: ${l.correct??'—'}; проверенных попыток: ${l.total??'—'}. Оценка освоения доступна на карте знаний.`:'Прогресс сохранён. Можно продолжить, если позволяет лимит.'}</div>`}
  <hr class="divider"><div class="row">${l.status==='paused'?'<button class="primary" data-action="resume">Продолжить</button>':''}${l.status==='active'?'<button data-action="pause">Сохранить и приостановить</button><button data-action="complete">Завершить занятие</button>':''}<button data-action="route" data-value="knowledge">Карта знаний</button></div></section>`;
}
function homeworkPage(){return learningPage();}
function legacyHomeworkPage() {
  const h=state.homework;
  const chosen=state.hwSubject||'';
  const topics=state.data.catalog.filter(t=>t.subject===chosen);
  return `<h1>Разберём домашнее задание</h1><p class="muted">Выбери предмет, затем введи условие и своё решение. Репетитор поможет найти первый затруднительный шаг.</p>
  <section class="card"><label>Предмет ДЗ (обязательно)<select id="homework-subject"><option value="">Выберите предмет…</option>${Object.entries(subjects).map(([id,label])=>`<option value="${id}" ${id===chosen?'selected':''}>${esc(label)}</option>`).join('')}</select></label>
  <label>Тема<select id="homework-topic"><option value="">Не определена — уточнить при проверке</option>${topics.map(t=>`<option value="${t.id}" ${state.hwTopic===t.id?'selected':''}>${esc(t.title)}</option>`).join('')}</select></label>
  <div class="row"><button data-action="file">Прикрепить файл</button><span class="muted">TXT, PY, CSV, PDF, DOCX, изображения · до 8 МБ</span></div>
  ${h?.filename?`<div class="callout">${esc(h.filename)}<br>${esc(h.warning||'')}</div>`:''}
  <form data-form="homework"><label>Условие и решение<textarea id="homework-draft" name="text" maxlength="60000" data-text-limit="30000" required placeholder="Условие: …&#10;Моё решение: …">${esc(h?.text||'')}</textarea></label>
  <p class="muted">Для файла с заданиями разных предметов проверяй каждую часть отдельно. OCR и vision ещё не подключены.</p>
  <label class="check"><input name="confirmed" type="checkbox" required>Я подтверждаю предмет и проверил текст задания</label><button class="primary" type="submit">Получить наводящую подсказку</button></form>
  ${state.homeworkResult?`<div class="callout">${esc(subjects[chosen])}: ответ ИИ не прошёл независимую предметную проверку.</div><pre>${esc(state.homeworkResult)}</pre>`:''}</section>
  ${chosen==='informatics'?`<section class="card" id="python-panel"><h2>Проверить синтаксис Python</h2><p>Код анализируется без исполнения. Результат не подтверждает правильность алгоритма.</p><form data-form="code"><textarea id="code-draft" name="code" required maxlength="60000" data-text-limit="30000" placeholder="Вставь код…"></textarea><button type="submit">Проверить синтаксис</button></form>${state.codeResult?`<pre>${esc(state.codeResult)}</pre>`:''}</section>`:''}`;
}
function knowledge() {
  const s=student();
  const items=(s?.knowledge||[]).filter(k=>!state.knowledgeSubject||k.subject===state.knowledgeSubject);
  return `<h1>Карта знаний</h1><p class="muted">Освоение — расчётная оценка по попыткам и подсказкам, не школьная отметка.</p>${subjectFilter('knowledge-subject',state.knowledgeSubject,true)}<section class="card">${items.length?`<table><thead><tr><th>Предмет / тема</th><th>Освоение</th><th>Уверенность</th><th>Ответы</th><th>Повторение</th></tr></thead><tbody>${items.map(k=>`<tr><td><small>${esc(k.subject_label||subjects[k.subject]||'Предмет не определён')}</small><br>${esc(k.topic_title||state.data.catalog.find(t=>t.id===k.topic)?.title||k.topic)}</td><td><progress max="100" value="${k.mastery_score}"></progress> ${k.mastery_score}%</td><td>${Math.round(k.confidence*100)}%</td><td>${k.correct_count}/${k.attempts_count}</td><td>${formatDate(k.next_review_at)}</td></tr>`).join('')}</tbody></table>`:'<p class="empty">По выбранному предмету пока недостаточно наблюдений.</p>'}</section>`;
}
function history() {
  const s=student(),sessions=s?.sessions||[];
  const period=state.period||7,cutoff=Date.now()-period*86400000;
  const filtered=sessions.filter(l=>new Date(l.created).getTime()>=cutoff&&(!state.reportSubject||(l.catalog_subject||l.subject)===state.reportSubject));
  return `<h1>История и отчёты</h1>${subjectFilter('history-subject',state.reportSubject,true)}<div class="row"><button data-action="period" data-value="7">За неделю</button><button data-action="period" data-value="30">За месяц</button><button data-action="period" data-value="36500">Вся история</button></div><section class="card"><h2>${filtered.length} занятий · ${minutes(filtered.reduce((n,l)=>n+l.seconds,0))} мин активного времени</h2>${filtered.length?`<table><thead><tr><th>Предмет / тема / дата</th><th>Состояние</th><th>Ответы</th><th></th></tr></thead><tbody>${filtered.map(l=>`<tr><td><small>${esc(subjectDisplay(l))}</small><br>${esc(l.title)}<br><small>${formatDate(l.created)}</small></td><td>${esc({active:'Активно',paused:'Пауза',complete:'Завершено'}[l.status])}</td><td>${l.correct??'—'}/${l.total??'—'}</td><td><button data-action="open-session" data-value="${l.id}">Открыть</button></td></tr>`).join('')}</tbody></table>`:'<p class="empty">За этот период и предмет занятий нет.</p>'}</section>${state.report?`<section class="card"><h2>${esc(state.report.title)}</h2><p>${esc(subjectDisplay(state.report))}</p><p class="muted">Программа на момент занятия: ${esc(JSON.stringify(state.report.program_snapshot))}</p>${(state.report.messages||[]).map(m=>`<div class="message">${renderRich(m.text)}</div>`).join('')}</section>`:''}`;
}
function studentsPage() {
  const s=student();
  return `<h1>Профили и семейные связи</h1>${profileButtons()}<div class="split"><section class="card"><h2>Создать профиль</h2><form data-form="register">${registerFields()}<button class="primary" type="submit">Создать</button></form></section><div><section class="card"><h2>Подключить второго родителя</h2><p>Сначала создайте его отдельный профиль. Связанный родитель выдаёт одноразовый код, новый родитель вводит его после входа. Код действует 10 минут.</p>${s?'<button data-action="invite">Создать код для выбранного ученика</button>':''}<form data-form="link"><label>Одноразовый код<input name="token" required autocomplete="off"></label><button type="submit">Подтвердить связь</button></form></section>${s?`<section class="card"><h2>Сброс пароля: ${esc(s.name)}</h2><form data-form="reset"><label>Новый пароль<input type="password" name="password" minlength="10" required></label><button type="submit">Сбросить пароль</button></form><p class="muted">Идентификатор ученика:<br>${esc(s.id)}</p></section>`:''}</div></div>`;
}
function controls() {
  const s=student();
  return `<h1>Учебное время</h1>${s?`<section class="card"><h2>${esc(s.name)}</h2><p>Сегодня: ${minutes(s.daily.seconds)} мин из ${s.controls.minutes}. После достижения лимита новое занятие недоступно. На текущее задание — до 15 дополнительных минут.</p><form data-form="controls"><label>Дневной лимит, минуты<input type="number" name="minutes" value="${s.controls.minutes}" min="5" max="240" required></label><button class="primary">Сохранить лимит</button></form><p class="muted">После трёх минут без учебных действий занятие приостанавливается.</p></section>`:'<p>Сначала добавьте ученика.</p>'}`;
}
function program(){return learningPage();}
function legacyProgram() {
  const s=student(),parent=state.data.user.role==='PARENT';
  const assignments=s?Object.entries(subjects).map(([id,label])=>{
    const p=s.programs?.[id]||{};
    return `<section class="card"><h3>${esc(label)}</h3>${p.title?`<p>${esc(p.title)}<br>${esc(p.authors)} · ${esc(p.publisher)}</p>`:'<p class="muted">Учебник пока не выбран.</p>'}</section>`;
  }).join(''):'';
  return `<h1>Учебники и программы</h1><div class="grid">${assignments}</div>
  ${s?.program.needs_subject_confirmation?`<div class="callout">Прежнее назначение сохранено в архиве. Создайте отдельный запрос для алгебры или геометрии.<pre>${esc(JSON.stringify(s.program,null,2))}</pre></div>`:''}
  <p class="muted">Автоматический поиск школьных программ пока не подключён. Учебники подтверждает родитель.</p>
  ${!parent?`<section class="card"><form data-form="program"><label>Предмет<select name="subject">${Object.entries(subjects).map(([k,v])=>`<option value="${k}">${esc(v)}</option>`).join('')}</select></label><label>Название учебника<input name="title" required maxlength="200"></label><label>Авторы<input name="authors" required maxlength="200"></label><label>Издательство<input name="publisher" required maxlength="200"></label><button class="primary">Запросить изменение</button></form></section>`:''}
  <h2>Запросы изменений</h2>${state.data.approvals.length?state.data.approvals.map(a=>`<section class="card"><h3>${esc(subjects[a.program.subject]||'Математика — архив')}</h3><p>${esc(a.program.title)} · ${esc(a.program.authors)} · ${esc(a.program.publisher)}</p><span class="badge">${esc(a.status)}</span>${parent&&a.status==='pending'?`<div class="row"><button data-action="approve" data-value="${a.id}">Подтвердить</button><button data-action="reject" data-value="${a.id}">Отклонить</button></div>`:''}</section>`).join(''):'<p class="muted">Запросов пока нет.</p>'}`;
}
function providers() {
  const c=state.data.provider||{};
  return `<h1>Подключение ИИ</h1><p class="muted">Настройка общая для семейной группы. Ключ хранится в зашифрованном хранилище и не возвращается интерфейсу.</p><section class="card"><form data-form="provider"><div class="field-grid"><label>Провайдер<select id="provider-kind" name="kind">${['openai','gigachat','qwen','ollama'].map(k=>`<option value="${k}" ${k===(c.kind||'ollama')?'selected':''}>${{openai:'OpenAI',gigachat:'GigaChat',qwen:'Qwen',ollama:'Ollama (локальный)'}[k]}</option>`).join('')}</select></label><label>Название<input name="name" value="${esc(c.name||'Семейное подключение')}" maxlength="100"></label></div><label>Модель<input name="model" value="${esc(c.model||'')}" required placeholder="Название установленной / доступной модели"></label><label>Endpoint (пусто — стандартный адрес)<input id="provider-endpoint" name="endpoint" value="${esc(c.endpoint||'')}" placeholder="Для Ollama: http://127.0.0.1:11434"></label><label>API-ключ / Basic-ключ GigaChat<input name="secret" type="password" autocomplete="off" placeholder="Пусто — сохранить прежний ключ этого провайдера"></label><label>Тайм-аут, секунды<input name="timeout" type="number" min="1" max="180" value="${c.timeout||60}"></label><label>Scope GigaChat<select name="scope">${['GIGACHAT_API_PERS','GIGACHAT_API_B2B','GIGACHAT_API_CORP'].map(s=>`<option ${s===c.scope?'selected':''}>${s}</option>`).join('')}</select></label><h3>Разрешения на облачную обработку</h3><label class="check"><input name="allow_text" type="checkbox" ${c.allow_text?'checked':''}>Разрешаю передавать учебный текст выбранному облачному провайдеру</label><label class="check"><input name="allow_documents" type="checkbox" ${c.allow_documents?'checked':''}>Разрешаю передавать подтверждённый текст документов и ДЗ</label><p class="muted">Имена, школа и семейные данные не включаются в контекст по умолчанию. Для OCR через GigaChat фотографии передаются только с отдельным разрешением ниже. Аудио в облако не отправляется. Для GigaChat может требоваться доверенный корневой сертификат в Windows; проверка TLS не отключается.</p><button class="primary">Сохранить подключение и разрешения</button></form><hr class="divider"><div class="row"><button data-action="test-provider">Проверить текстовый запрос</button><button data-action="models">Получить список моделей</button></div>${state.providerResult?`<pre>${esc(state.providerResult)}</pre>`:''}</section>`;
}
function backup() {
  return `<h1>Резервные копии Tutor-AI</h1><div class="callout">База и вложения зашифрованы всегда. Ручная копия дополнительно защищается отдельным паролем. Автокопии создаются после входа родителя раз в сутки и используют ключ текущего хранилища.</div><div class="split"><section class="card"><h2>Создать копию</h2><form data-form="backup"><label>Пароль архива<input name="password" type="password" minlength="10" required autocomplete="new-password"></label><button class="primary">Создать резервную копию</button></form><p class="muted">Последняя копия: ${formatDate(state.data.backup.last_at)}<br>${esc(state.data.backup.last_file||'Копий ещё нет')}</p><p class="muted">Копии находятся в app-data/backups рядом с приложением. Сохраните пароль архива и данные входа из копии отдельно.</p></section><section class="card"><h2>Восстановить</h2><p>Восстановление заменит текущее состояние. Перед заменой сохраняется его зашифрованный снимок.</p><form data-form="restore"><label>Имя файла в app-data/backups<input name="filename" required placeholder="20261025-….aitbackup"></label><label>Пароль архива (для ручной копии)<input name="password" type="password"></label><label>ID родителя из копии<input name="account" required></label><label>Пароль родителя из копии<input name="account_password" type="password" required></label><label class="check"><input type="checkbox" required>Подтверждаю замену текущего состояния</label><button class="danger">Проверить и восстановить</button></form></section></div>`;
}
function security() {
  const events=state.data.audit.slice(-20).reverse().map(a=>`<article class="audit-event"><small>${formatDate(a.at)}</small><h3>${esc(a.label)}</h3>
    <p>Автор: ${esc(a.actor_display.name)}${a.actor_display.role?' · '+roleName(a.actor_display.role):''}</p>
    ${a.target?`<p>Профиль: ${esc(a.target_display.name)} · ${roleName(a.target_display.role)}</p>`:''}
    ${a.actor_current_name?`<small>Текущее имя автора: ${esc(a.actor_current_name)}</small>`:''}
    <details><summary>Технические сведения</summary><small>Код: ${esc(a.event)}<br>Автор ID: ${esc(a.actor||'Приложение')}<br>Цель ID: ${esc(a.target||'—')}</small></details></article>`).join('');
  return `<h1>Безопасность</h1><div class="split"><section class="card"><h2>Сменить пароль</h2><form data-form="password"><label>Новый пароль<input type="password" name="password" minlength="10" required></label><button>Сменить пароль</button></form><hr class="divider"><h2>Ключ восстановления</h2><p>Перевыпуск аннулирует прежний ключ для текущего хранилища. Старые резервные копии сохраняют старые ключевые обёртки.</p><button data-action="rotate-recovery">Создать новый ключ восстановления</button></section><section class="card"><h2>Журнал безопасности</h2><small>Время показано в часовом поясе компьютера: ${esc(Intl.DateTimeFormat().resolvedOptions().timeZone)}</small>${events||'<p>Событий пока нет.</p>'}</section></div>`;
}
function settings() {
  const theme=state.data.user.theme;
  const renameCard=`<section class="card"><h2>Мой профиль</h2><p>${esc(state.data.user.name)}</p><button data-action="edit-profile" data-value="${esc(state.data.user.id)}">Редактировать мои данные</button></section>`;
  return `<h1>Настройки</h1>${renameCard}<section class="card"><h2>Оформление</h2><form data-form="theme"><label>Дизайн<select name="design">${[["strict","Строгий"],["modern","Современная"]].map(([k,v])=>`<option value="${k}" ${k===state.data.user.design?"selected":""}>${v}</option>`).join("")}</select></label><label>Цветовая тема<select name="theme">${[['system','Как в системе'],['light','Светлая'],['dark','Тёмная']].map(([k,v])=>`<option value="${k}" ${k===theme?'selected':''}>${v}</option>`).join('')}</select></label><button class="primary">Сохранить</button></form></section><section class="card"><h2>Доступ к профилю</h2><p>Идентификатор входа: <strong>${esc(state.data.user.id)}</strong></p><form data-form="password"><label>Новый пароль<input name="password" type="password" minlength="10" required></label><button>Сменить пароль</button></form><hr class="divider"><button data-action="logout">Выйти и заблокировать хранилище</button></section>${state.data.user.role==='STUDENT'&&!state.data.has_parent?`<section class="card"><h2>Подключить первого родителя</h2><form data-form="register">${registerFields()}<button class="primary">Создать профиль родителя</button></form></section>`:''}<section class="card"><h2>О версии</h2><p>0.5.0a4 · Python / Qt WebEngine. Полная приёмка MVP не пройдена. Короткий PIN, автоматический школьный справочник, потоковая генерация и диктовка пока недоступны. OCR через GigaChat находится в предварительной версии; фотографии требуют отдельного разрешения. Системное озвучивание работает при наличии голоса Windows.</p></section>`;
}

document.addEventListener('input',e=>{
  if(e.target.id.endsWith('-draft'))state.drafts[e.target.id]=e.target.value;
  if(e.target.dataset.textLimit)validateTextLimit(e.target);
});
document.addEventListener('change',e=>{
  if(e.target.id==='selected-student'){if(!discardProfile()){e.target.value=state.selected;return;}state.selected=e.target.value;state.report=null;if(state.route==='profile')state.route='students';render();}
  if(e.target.id==='provider-kind') $('#provider-endpoint').value='';
  if(e.target.id==='homework-subject'){state.hwSubject=e.target.value;state.hwTopic=null;state.homeworkResult=null;state.codeResult=null;render();}
  if(e.target.id==='homework-topic'){state.hwTopic=e.target.value||null;state.homeworkResult=null;render();}
  if(e.target.id==='knowledge-subject'){state.knowledgeSubject=e.target.value;render();}
  if(e.target.id==='history-subject'){state.reportSubject=e.target.value;state.report=null;render();}
});
document.addEventListener('click',e=>{
  const button=e.target.closest('[data-action]'); if(!button)return;
  const action=button.dataset.action,value=button.dataset.value;
  if(button.disabled||(inFlight&&action!=='route'))return;
  if(inFlight&&state.profileDirty&&action==='route'){notify('Дождитесь завершения сохранения анкеты. Переход не отменяет уже отправленные изменения.');return;}
  if(['route','logout','edit-profile','reload-profile','cancel-profile'].includes(action)&&!discardProfile())return;
  if(action==='cancel-profile'){state.profileEdit=null;state.route=state.profileReturn||(state.data.user.role==='PARENT'?'students':'settings');render();return;}
  if(action==='route'){navigate(value);return;}
  if(action==='auth'){state.authMode=value;render();return;}
  if(action==='subject'){state.subject=value;state.route='subjects';render();return;}
  if(action==='subject-homework'){selectLearningSubject(value);state.homeworkResult=null;state.route='homework';render();return;}
  if(action==='diagnose'||action==='subject-diagnose'){state.learnSubject=state.subject;state.route='learning';render();return;}
  if(action==='period'){state.period=Number(value);render();return;}
  perform(async()=>{
    if(action==='choose-transfer'){const plan=await rpc('choose_transfer',{separate:$('#transfer-separate').checked});if(plan){state.transferPlan=plan;render();}return;}
    if(action==='recover-transfer'||action==='choose-transfer-recovery'){await rpc(action==='recover-transfer'?'recover_transfer':'choose_transfer_recovery');await refresh();notify('Проверка завершена. Источник сохранён; при необходимости выберите папки заново.');return;}
    if(action==='launch-transfer'){await rpc('launch_transferred');notify('Запущена новая установка. Войдите в существующий профиль.');return;}
    if(action==='edit-profile'||action==='reload-profile'){await openProfile(action==='reload-profile'?state.profileEdit.id:value);return;}
    if(action==='read-notification'){await rpc('read_notification',{notification:value});await refresh();return;}
    if(action==='notification-profile'){const n=state.data.notifications.find(n=>n.id===value);await openProfile(n.student);await rpc('read_notification',{notification:value});await refresh();return;}
    if(action==='logout'){await rpc('logout');state.lesson=null;state.drafts={};state.homework=null;state.hwSubject=null;state.hwTopic=null;state.subject=null;state.report=null;state.homeworkResult=null;state.codeResult=null;state.providerResult=null;state.route='home';state.authMode='login';await refresh();}
    else if(['start','diagnose','subject-diagnose'].includes(action)){
      await refreshLearningState();const active=student()?.sessions.find(s=>s.status==='active');
      if(active){if(!await askPause(active.title))return;await rpc('pause',{session:active.id});}
      state.lesson=await rpc('start_lesson',{topic_id:value,mode:{start:'learn',diagnose:'diagnose','subject-diagnose':'subject_diagnose'}[action]});operationRoute('lesson');render();
    }
    else if(['pause','resume','complete','hint'].includes(action)){state.lesson=await rpc(action,{session:state.lesson.id});await refresh();}
    else if(action==='open-session'){const l=student().sessions.find(s=>s.id===value);if(state.data.user.role==='PARENT')state.report=l;else{state.lesson=l;state.route='lesson';}render();}
    else if(action==='file'){const h=await rpc('pick_file');if(h){state.homework=h;delete state.drafts['homework-draft'];state.homeworkResult=null;render();}}
    else if(action==='speak'){const text=[...state.lesson.messages].reverse().find(m=>m.role==='assistant')?.text;await rpc('speak',{text});}
    else if(action==='invite'){const result=await rpc('create_invite',{student:student().id});$('#secret-value').textContent='Одноразовый код связи (10 минут):\n'+result.token;$('#secret').showModal();}
    else if(action==='test-provider'){const r=await rpc('test_provider');state.providerResult='Подключение работает.\n'+r.text+'\nТокены: '+JSON.stringify(r.usage);render();}
    else if(action==='models'){const r=await rpc('list_models');state.providerResult=JSON.stringify(r,null,2);render();}
    else if(action==='rotate-recovery'){const r=await rpc('rotate_recovery');showSecrets(r);}
    else if(action==='approve'||action==='reject'){await rpc('approve_program',{request:value,accept:action==='approve'});await refresh();}
  });
});
document.addEventListener('submit',e=>{
  const form=e.target.closest('[data-form]');if(!form)return;e.preventDefault();
  const kind=form.dataset.form,fd=new FormData(form),v=Object.fromEntries(fd.entries());
  perform(async()=>{
    if(kind==='transfer'){
      const args={operation:state.transferPlan.id,account:v.account,password:v.password};form.reset();
      const result=await rpc('run_transfer',args);delete args.password;await refresh();
      if(!result.current){state.transferDone=result;render();}
      notify('Перенос завершён. Войдите в существующий профиль; источник сохранён.');return;
    }
    if(kind==='login'){const result=await rpc('login',v);form.reset();state.route='home';await refresh();if(result.directory_warning)notify('Открытый список профилей был повреждён и восстановлен по зашифрованной базе.');}
    else if(kind==='register'){const address=v.role==='STUDENT'?addressPayload(form):undefined;const result=await rpc('register',{name:v.name,password:v.password,role:v.role,profile:{region:v.region,city:v.city,school:v.school,grade:7,address}});form.reset();await refresh();showSecrets(result);}
    else if(kind==='recover'){await rpc('recover',v);form.reset();state.authMode='login';await refresh();notify('Доступ восстановлен. Войдите с новым паролем.');}
    else if(kind==='answer'){
      if(state.answerOperation?.session!==state.lesson.id||state.answerOperation?.answer!==v.answer)
        state.answerOperation={session:state.lesson.id,answer:v.answer,operation_id:crypto.randomUUID()};
      const r=await rpc('answer',state.answerOperation);state.lesson=r.session;
      delete state.answerOperation;delete state.drafts['answer-draft'];await refresh();
    }
    else if(kind==='chat'){state.lesson=await rpc('chat',{session:state.lesson.id,text:v.text});delete state.drafts['question-draft'];render();}
    else if(kind==='homework'){
      if(!state.hwSubject)throw new Error('Выберите предмет домашнего задания.');
      state.homework=await rpc('prepare_homework',{subject:state.hwSubject,topic_id:state.hwTopic||null,homework:state.homework?.id||null});
      if(state.homework.text_reextracted){
        state.drafts['homework-draft']=state.homework.text;state.homeworkResult=null;render();
        notify('Старый файл извлечён заново. Проверьте полный текст и подтвердите его перед отправкой.');return;
      }
      await rpc('confirm_homework',{homework:state.homework.id,text:v.text});
      await refreshLearningState();
      const active=student()?.sessions.find(s=>s.status==='active');
      if(active && !(active.mode==='homework'&&active.homework===state.homework.id&&active.subject===state.hwSubject&&active.topic===(state.hwTopic||null))){
        if(!await askPause(active.title))return;
        await rpc('pause',{session:active.id});
      }
      const r=await rpc('check_homework',{text:v.text,subject:state.hwSubject,topic_id:state.hwTopic||null,homework:state.homework.id});state.homeworkResult=r.text;await refreshLearningState();state.lesson=student()?.sessions.find(s=>s.status==='active')||state.lesson;render();
    }
    else if(kind==='code'){
      if(state.hwSubject!=='informatics')throw new Error('Проверка Python доступна только для информатики.');
      state.homework=await rpc('prepare_homework',{subject:'informatics',topic_id:state.hwTopic||null,homework:state.homework?.id||null});
      const r=await rpc('analyze_code',{code:v.code,homework:state.homework.id});state.codeResult=r.text;render();
    }
    else if(kind==='provider'){await rpc('save_provider',{config:{...v,timeout:Number(v.timeout),revision:state.data.provider.revision||0,allow_text:fd.has('allow_text'),allow_documents:fd.has('allow_documents'),allow_images:fd.has('allow_images')}});form.reset();await refresh();notify('Подключение и разрешения сохранены.');}
    else if(kind==='controls'){await rpc('set_controls',{student:student().id,minutes:Number(v.minutes),revision:student().controls.revision});await refresh();notify('Лимит сохранён.');}
    else if(kind==='profile'){
      try {
        const p=state.profileEdit;
        const changes={name:v.name,...(p.role==='STUDENT'?{region:v.region,city:v.city,school:v.school,address:addressPayload(form)}:{})};
        const result=await rpc('save_profile',{account:p.id,revision:p.revision,changes});
        state.profileDirty=false;state.profileEdit=null;operationRoute(state.profileReturn||(state.data.user.role==='PARENT'?'students':'settings'));
        await refresh();notify(result.changed?'Данные сохранены.'+(result.notifications?' Родители получат уведомление.':''):'Изменений нет.');
      } catch(error){if(!error.stale&&$('#profile-error'))$('#profile-error').textContent=error.message;throw error;}
    }
    else if(kind==='theme'){await rpc('set_theme',v);await refresh();notify('Оформление сохранено');}
    else if(kind==='rename'){await rpc('rename_profile',v);await refresh();notify('Имя профиля обновлено. Идентификатор и история сохранены.');}
    else if(kind==='password'){await rpc('change_password',v);form.reset();notify('Пароль изменён.');}
    else if(kind==='reset'){await rpc('reset_password',{student:student().id,password:v.password});form.reset();notify('Пароль ученика изменён.');}
    else if(kind==='link'){await rpc('link',v);form.reset();await refresh();notify('Связь подтверждена.');}
    else if(kind==='backup'){const r=await rpc('backup',v);form.reset();await refresh();notify('Создана копия: '+r.file);}
    else if(kind==='restore'){const r=await rpc('restore',v);form.reset();state.lesson=null;state.drafts={};await refresh();notify(r.message);}
    else if(kind==='program'){await rpc('request_program',{program:{...v,grade:7,source:'Ручной выбор',verification:'pending'}});form.reset();await refresh();notify('Запрос передан родителю.');}
  });
});

function receiveResponse(id,payload) {
      const job=pending.get(id);if(!job)return;clearTimeout(job.timer);pending.delete(id);
      try{
        if(job.epoch!==contextEpoch){job.reject(staleContext());return;}
        const value=JSON.parse(payload);
        if(value.error){
          if(value.code==='authentication'&&state.data){resetPersonalState(nativeContext);void refresh().catch(()=>{});job.reject(staleContext());}
          else job.reject(Object.assign(new Error(value.error),{code:value.code}));
          return;
        }
        const context=value.result?.context;
        if(context&&nativeContext&&context!==nativeContext){
          resetPersonalState(context);
          if(job.command==='snapshot'){void refresh().catch(()=>{});job.reject(staleContext());return;}
        }
        if(context)nativeContext=context;
        job.resolve(value.result);
      }catch{job.reject(new Error('Некорректный ответ нативного слоя.'));}
}

if(typeof qt!=='undefined') {
  new QWebChannel(qt.webChannelTransport, channel=>{
    bridge=channel.objects.native;
    bridge.response.connect(receiveResponse);
    bridge.checkpointFailed?.connect(failed=>{
      const warning=$('#checkpoint-warning');
      warning.hidden=!failed;
    });
    perform(refresh);
  });
} else { $('#app').innerHTML='<main class="welcome"><h1>Запустите настольное приложение</h1><p>Этот интерфейс работает через защищённый нативный слой. Выполните main.py или запустите Tutor-AI.exe.</p></main>'; }
