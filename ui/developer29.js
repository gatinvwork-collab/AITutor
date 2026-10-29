'use strict';
let developerClicks29=0;
const developerDialog29=document.createElement('dialog');developerDialog29.id='developer29';
developerDialog29.innerHTML='<h2>Вход разработчика</h2><form id="developer-unlock29"><label>Пароль<input name="password" type="password" autocomplete="off" required></label><button>Войти</button><button type="button" id="developer-cancel29">Отмена</button></form>';
document.body.append(developerDialog29);
document.addEventListener('click',e=>{
 const label=e.target.closest('#developer-entry29');if(!label)return;
 developerClicks29++;if(developerClicks29===10){developerClicks29=0;developerDialog29.showModal();developerDialog29.querySelector('input').focus();}
});
function resetDeveloperClicks29(){developerClicks29=0;}
document.querySelector('#developer-cancel29').onclick=()=>{developerDialog29.close();developerDialog29.querySelector('input').value='';resetDeveloperClicks29();};
developerDialog29.addEventListener('cancel',()=>{developerDialog29.querySelector('input').value='';resetDeveloperClicks29();});
developerDialog29.addEventListener('close',()=>{developerDialog29.querySelector('input').value='';resetDeveloperClicks29();});
document.querySelector('#developer-unlock29').onsubmit=async e=>{
 e.preventDefault();const input=e.target.elements.password,password=input.value;input.value='';
 try{const status=await rpc('developer',{action:'unlock',password});state.developer29=status;developerDialog29.close();render();}
 catch(error){notify(error.message);developerDialog29.close();}finally{resetDeveloperClicks29();}
};
const settingsBefore29=settings;
settings=function(){const result=settingsBefore29();const wrapper=document.createElement('div');wrapper.innerHTML=result;
 const identity=[...wrapper.querySelectorAll('p')].find(p=>p.textContent.startsWith('Идентификатор входа:'));
 if(identity){identity.id='developer-entry29';identity.setAttribute('tabindex','0');}
 if(state.developer29?.unlocked){const section=document.createElement('section');section.className='card';section.innerHTML=`<h2>Диагностика разработчика</h2><p>Полный учебный журнал содержит персональные ответы. Внешней отправки нет. Сбор по умолчанию выключен; вход god не расширяет права профиля.</p><p>Сбор: ${state.developer29.enabled?'включён':'выключен'}${state.developer29.incomplete?' · неполный (ошибка или лимит)':''}</p><button data-dev29="toggle">${state.developer29.enabled?'Выключить':'Включить'} подробный сбор</button><button data-dev29="view">Просмотреть разрешённые записи</button><button data-dev29="export">Экспортировать JSON с учебными данными…</button>${state.data.user.role==='PARENT'?'<button data-dev29="clear">Очистить только диагностические файлы</button>':''}<button data-dev29="close">Выйти из режима</button><label>Начиная с даты<input id="developer-since29" type="date"></label><label>Job ID (необязательно)<input id="developer-job29"></label><label>Стадия<select id="developer-stage29"><option value="">Все</option><option>send</option><option>receive</option><option>terminal</option><option>transport_error</option></select></label><pre>${esc(state.developerEvents29?JSON.stringify(state.developerEvents29,null,2):'')}</pre>`;wrapper.append(section);}
 return wrapper.innerHTML;
};
document.addEventListener('click',e=>{const b=e.target.closest('[data-dev29]');if(!b)return;
 perform(async()=>{const action=b.dataset.dev29;
 const filters={student:state.selected,since:$('#developer-since29')?.value?new Date($('#developer-since29').value).getTime()/1000:0,
   job:$('#developer-job29')?.value||null,stage:$('#developer-stage29')?.value||null};
 if(action==='export'){await rpc('export_trace',filters);return;}
 const args={action:action==='toggle'?'enable':action,...filters};if(action==='toggle')args.enabled=!state.developer29.enabled;
 const result=await rpc('developer',args);if(action==='view')state.developerEvents29=result;else state.developer29=result;
 if(action==='close')state.developerEvents29=null;render();});
});
const navigateBeforeDev29=navigate;
navigate=function(route){resetDeveloperClicks29();if(developerDialog29.open)developerDialog29.close();navigateBeforeDev29(route);};
