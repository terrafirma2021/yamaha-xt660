// The overview selects a real static route. Other pages need no selector script.
(() => {
  const form=document.getElementById('bike-form');
  if(!form)return;
  const data=JSON.parse(document.getElementById('bike-choices').textContent);
  const fields=Object.fromEntries(['model','year','market','ecu','firmware'].map(k=>[k,document.getElementById('choose-'+k)]));
  const initial=data.records.find(r=>r.key===data.selected);
  if(!initial)return;
  let selected=initial;
  function options(field,choices,preferred){
    field.replaceChildren(...choices.map(c=>{
      const option=new Option(c.label,c.value);
      option.disabled=!!c.disabled;
      return option;
    }));
    field.value=choices.some(c=>c.value===preferred&&!c.disabled)?preferred:choices.find(c=>!c.disabled).value;
  }
  function update(preferred){
    options(fields.model,data.models.map(m=>({value:m.id,label:m.name+(data.records.some(r=>r.model===m.id)?'':' — No BIN yet'),disabled:!data.records.some(r=>r.model===m.id)})),preferred.model);
    let available=data.records.filter(r=>r.model===fields.model.value);
    for(const key of ['year','market','ecu']){
      const values=[...new Set(available.map(r=>r[key]))];
      if(key==='year')values.sort((a,b)=>Number(a)-Number(b));
      options(fields[key],values.map(value=>({value,label:value})),preferred[key]);
      available=available.filter(r=>r[key]===fields[key].value);
    }
    options(fields.firmware,available.map(r=>({value:r.key,label:r.firmware})),preferred.firmware);
    selected=available.find(r=>r.key===fields.firmware.value);
  }
  for(const field of Object.values(fields))field.addEventListener('change',()=>update(Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.value]))));
  form.addEventListener('submit',event=>{
    event.preventDefault();
    const destination=new URL(selected.path,location.href);
    if(destination.origin===location.origin)location.assign(destination.href);
  });
  update({...initial,firmware:initial.key});
  form.hidden=false;
  document.getElementById('bike-fallback').hidden=true;
})();
