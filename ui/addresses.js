'use strict';

function addressFields() {
  return `<div class="address-fields">
    <p class="muted">Адресные подсказки: Photon / OpenStreetMap, не ФИАС. В интернет передаётся только адресный запрос.</p>
    <label class="check"><input type="checkbox" name="manual_address">Ввести адрес вручную (без подтверждения справочником)</label>
    <div class="field-grid"><div><label>Регион<input name="region" class="address-region" maxlength="200" autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="region-options"></label><div id="region-options" class="address-options" role="listbox"></div></div>
    <div><label>Город / населённый пункт<input name="city" class="address-city" maxlength="200" autocomplete="off" disabled role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="city-options"></label><div id="city-options" class="address-options" role="listbox"></div></div></div>
    <p class="muted address-status" role="status" aria-live="polite">Введите не менее двух букв региона и выберите подсказку. Для профиля родителя адрес не требуется.</p>
  </div>`;
}

const addressForms = new WeakMap();
function addressState(form) {
  if(!addressForms.has(form)) addressForms.set(form, {region:null,city:null,regionSeq:0,citySeq:0,timers:{}});
  return addressForms.get(form);
}
function fillAddress(form, profile) {
  const data=addressState(form), address=profile.address||{};
  form.elements.region.value=profile.region||'';
  form.elements.city.value=profile.city||'';
  form.elements.school.value=profile.school||'';
  data.region=address.region||null; data.city=address.city||null;
  form.elements.manual_address.checked=address.mode!=='catalog';
  form.elements.city.disabled=false;
  addressMessage(form,address.mode==='catalog'?'Сохранённый адрес из справочника. Повторный поиск не требуется.':'Сохранённый ручной адрес. При необходимости выберите записи из справочника.');
}
function clearOptions(form, kind) {
  form.querySelector(`#${kind}-options`).replaceChildren();
  form.querySelector(`[name="${kind}"]`).setAttribute('aria-expanded','false');
}
function addressPayload(form) {
  const data=addressState(form);
  if(form.elements.manual_address.checked) return {mode:'manual'};
  if(!data.region || !data.city) throw new Error('Выберите регион и город из подсказок либо включите ручной ввод.');
  return {mode:'catalog',region_id:data.region.id,city_id:data.city.id};
}
function addressMessage(form,text) {form.querySelector('.address-status').textContent=text;}
function queueAddress(form,kind) {
  const state=addressState(form),field=form.elements[kind],query=field.value;
  const seq=++state[kind+'Seq'];
  clearTimeout(state.timers[kind]);clearOptions(form,kind);
  if(query.trim().length<2 || form.elements.manual_address.checked)return;
  const parent=state.region?.id||null;
  if(kind==='city'&&!parent)return;
  addressMessage(form,'Поиск…');
  state.timers[kind]=setTimeout(async()=>{
    try {
      const result=await rpc('search_addresses',{kind,query,region_id:parent});
      if(!form.isConnected || seq!==state[kind+'Seq'] || (kind==='city'&&parent!==state.region?.id) || form.elements.manual_address.checked)return;
      const list=form.querySelector(`#${kind}-options`);
      for(const record of result.items) {
        const button=document.createElement('button');button.type='button';button.role='option';button.textContent=record.label;
        button.addEventListener('click',()=>{
          state[kind]=record;field.value=record.name;++state[kind+'Seq'];clearOptions(form,kind);
          if(kind==='region') {
            state.city=null;++state.citySeq;clearTimeout(state.timers.city);form.elements.city.value='';
            form.elements.city.disabled=false;form.elements.school.value='';clearOptions(form,'city');form.elements.city.focus();
          }
          addressMessage(form,kind==='region'?'Регион выбран. Теперь выберите город.':'Регион и город выбраны. Источник: Photon / OpenStreetMap.');
        });
        list.append(button);
      }
      field.setAttribute('aria-expanded',String(result.items.length>0));addressMessage(form,result.message);
    } catch(error) {
      if(!error.stale&&form.isConnected&&seq===state[kind+'Seq'])addressMessage(form,error.message);
    }
  },1150);
}
document.addEventListener('input',event=>{
  const field=event.target,form=field.closest('form');
  if(!form?.querySelector('.address-fields'))return;
  const kind=field.classList.contains('address-region')?'region':field.classList.contains('address-city')?'city':null;
  if(!kind)return;
  const state=addressState(form);state[kind]=null;
  if(kind==='region') {
    state.city=null;++state.citySeq;clearTimeout(state.timers.city);clearOptions(form,'city');
    form.elements.city.value='';form.elements.city.disabled=!form.elements.manual_address.checked;form.elements.school.value='';
  } else form.elements.school.value='';
  queueAddress(form,kind);
});
document.addEventListener('change',event=>{
  const field=event.target,form=field.closest('form');
  if(field.name!=='manual_address'||!form)return;
  const state=addressState(form);++state.regionSeq;++state.citySeq;
  clearTimeout(state.timers.region);clearTimeout(state.timers.city);state.region=state.city=null;
  clearOptions(form,'region');clearOptions(form,'city');form.elements.city.disabled=!field.checked;
  addressMessage(form,field.checked?'Ручной ввод: адрес сохранится как неподтверждённый.':'Повторно выберите регион и город из подсказок.');
});
