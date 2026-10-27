'use strict';

function profilePage() {
  const p=state.profileEdit;
  if(!p)return '<h1>Профиль</h1><p>Откройте профиль из настроек или списка семейных профилей.</p>';
  return `<h1>Редактирование профиля</h1><section class="card"><h2>${esc(p.name)} · ${roleName(p.role)}</h2>
    <p class="muted">Идентификатор: ${esc(p.id)}. Имя и роль видны в локальном списке входа.</p>
    <form data-form="profile"><label>Отображаемое имя<input name="name" value="${esc(p.name)}" maxlength="60" required></label>
    ${p.role==='STUDENT'?`${addressFields()}<label>Школа<input name="school" maxlength="200" required></label><label>Класс<input value="7" readonly></label>
    <p class="muted">При самостоятельной смене региона, города или школы связанные родители получат уведомление. Проверьте актуальность учебной программы: она меняется отдельно с подтверждением родителя.</p>`:''}
    <p id="profile-error" class="form-error" role="alert"></p><div class="row"><button class="primary">Сохранить</button>
    <button type="button" data-action="cancel-profile">Отмена</button><button type="button" data-action="reload-profile">Перечитать профиль</button></div></form></section>`;
}
function profileButtons() {
  return `<section class="card"><h2>Редактировать профиль</h2><p class="muted">Доступны свой профиль, связанные дети и родители с общим подтверждённым ребёнком.</p><div class="row">${state.data.editable_profiles.map(p=>`<button data-action="edit-profile" data-value="${esc(p.id)}">${esc(p.name)} · ${roleName(p.role)} · ${esc(p.id.slice(0,8))}</button>`).join('')}</div></section>`;
}
function notificationsPage() {
  const labels={region:'Регион',city:'Город',school:'Школа'};
  return `<h1>Уведомления</h1><p class="muted">Изменения анкеты ученик сохраняет самостоятельно. Уведомления не требуют подтверждения.</p>${state.data.notifications.map(n=>`<article class="card ${n.read_at?'':'unread'}"><span class="badge">${n.read_at?'Прочитано':'Новое'}</span><h2>${esc(n.student_name)} изменил(а) данные профиля</h2><small>${formatDate(n.at)} · Автор: ${esc(n.actor_name)}</small><dl>${Object.entries(n.changes).map(([k,v])=>`<dt>${labels[k]||esc(k)}</dt><dd>${esc(v.before)} → <strong>${esc(v.after)}</strong></dd>`).join('')}</dl>${n.changes.school?'<p>Проверьте актуальность учебной программы и учебников.</p>':''}<div class="row"><button data-action="notification-profile" data-value="${esc(n.id)}">Открыть профиль</button>${!n.read_at?`<button data-action="read-notification" data-value="${esc(n.id)}">Отметить прочитанным</button>`:''}</div></article>`).join('')||'<section class="card"><p>Уведомлений пока нет.</p></section>'}`;
}
function discardProfile() {
  if(state.profileDirty&&!window.confirm('Отбросить несохранённые изменения анкеты?'))return false;
  state.profileDirty=false;return true;
}
async function openProfile(account) {
  const result=await rpc('get_profile',{account});
  state.profileEdit=result;state.profileDirty=false;state.route='profile';render();
}
document.addEventListener('input',event=>{
  if(event.target.closest('form[data-form="profile"]'))state.profileDirty=true;
});
document.addEventListener('change',event=>{
  if(event.target.closest('form[data-form="profile"]'))state.profileDirty=true;
  const form=event.target.closest('form[data-form="theme"]');
  if(form)applyAppearance(form.elements.theme.value,form.elements.design.value);
});
