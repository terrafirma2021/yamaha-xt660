'use strict';
const $=id=>document.getElementById(id), token=document.querySelector('meta[name=session]').content;
const names=['Throttle','Intake pressure','O₂ input','Intake temperature','Supply monitor','Lean sensor','Coolant temperature','Auxiliary input'];
let loaded=false,busy=false,running=false,authAllowed=false,timer=null,queue=Promise.resolve();
const controls=['run','step','crank','stopCrank','authenticate','meter','verify','pitch'];
for(let n=0;n<8;n++){
  const row=document.createElement('div');row.className='sensor';
  const label=document.createElement('label');label.htmlFor='adc'+n;label.textContent=names[n];
  const slider=document.createElement('input');Object.assign(slider,{id:'adc'+n,type:'range',min:0,max:1023,value:512,disabled:true});
  slider.setAttribute('aria-label',names[n]+' ADC');
  const value=document.createElement('input');Object.assign(value,{id:'value'+n,type:'number',min:0,max:1023,value:512,disabled:true});value.setAttribute('aria-label',names[n]+' value');
  slider.oninput=()=>{value.value=slider.value;};
  slider.onchange=()=>act('adc',{channel:n,value:Number(slider.value)});
  value.onchange=()=>{if(value.checkValidity())act('adc',{channel:n,value:Number(value.value)});else value.reportValidity();};
  row.append(label,slider,value);$('sensors').append(row);
}
function lock(){
  $('load').disabled=busy||running;$('image').disabled=busy||running;
  for(const id of controls)$(id).disabled=!loaded||(busy&&!(id==='run'&&running))||(running&&id!=='run');
  $('authenticate').disabled||=!authAllowed;
  for(let n=0;n<8;n++)for(const prefix of ['adc','value'])$(prefix+n).disabled=!loaded;
  $('run').textContent=running?'Pause':'Run';$('running').textContent=running?'Running in instruction batches':'Paused';
  for(const id of ['traceLink','storageLink'])$(id).setAttribute('aria-disabled',String(!loaded||busy));
}
function wave(trace){
  const svg=$('wave'),ns='http://www.w3.org/2000/svg';svg.replaceChildren();
  const rows=trace.filter(e=>e.kind==='output'&&[3,6,7].includes(e.channel));
  if(!rows.length){const text=document.createElementNS(ns,'text');text.setAttribute('x',24);text.setAttribute('y',80);text.textContent='No output transitions in this trace window.';svg.append(text);return;}
  const start=rows[0].cycle,end=rows.at(-1).cycle,span=Math.max(1,end-start),x=t=>20+(t-start)*600/span;
  for(const [idx,ch] of [3,6,7].entries()){
    const events=rows.filter(e=>e.channel===ch),base=45+idx*45;
    const line=document.createElementNS(ns,'line');for(const [k,v] of Object.entries({x1:20,x2:620,y1:base,y2:base}))line.setAttribute(k,v);svg.append(line);
    if(!events.length)continue;
    let level=1-events[0].value,d=`M20 ${base-level*25}`;
    for(const e of events){d+=` H${x(e.cycle)} V${base-e.value*25}`;level=e.value;}d+=' H620';
    const path=document.createElementNS(ns,'path');path.setAttribute('d',d);path.setAttribute('stroke',['var(--coil)','var(--injector)','var(--secondary)'][idx]);svg.append(path);
  }
}
function render(s){
  loaded=s.loaded;
  if(!$('image').options.length)for(const image of s.images){const o=document.createElement('option');o.value=image.id;o.textContent=image.label;$('image').append(o);}
  if(s.error)throw Error(s.error);
  if(loaded){
    $('image').value=s.image;
    if(document.activeElement!==$('pitch')){$('pitch').value=s.crank_pitch;$('pitchLabel').textContent=s.crank_pitch+' ticks';}
    $('sync').textContent=s.synchronized?'Synchronized':'Waiting';$('pitchValue').textContent=s.pitch_ticks&&s.pitch_ticks!==65535?s.pitch_ticks:'—';
    authAllowed=s.authentication_required&&!s.authentication_complete;
    $('auth').textContent=!s.authentication_required?'Disabled in BIN':s.authentication_complete?'Accepted':s.authentication_inhibit?'Inhibited':'Pending';
    $('faults').textContent=s.faults.map(x=>x.toString(16).padStart(2,'0').toUpperCase()).join(' ');
    $('cycles').textContent=(s.counts.bus_cycles??0).toLocaleString()+' bus cycles';
    for(let n=0;n<8;n++)for(const prefix of ['adc','value']){const input=$(prefix+n);if(document.activeElement!==input)input.value=s.adc[n];}
    for(const [id,ch] of [['coil',3],['injector',6],['secondary',7]])$(id).textContent=s.output_transitions[ch];
    wave(s.trace);$('serial').textContent=s.transcript.length?s.transcript.map(r=>`TX ${r.request}  →  RX ${r.reply}`).join('\n'):'No exchanges yet.';$('serial').scrollTop=$('serial').scrollHeight;
  }
  lock();
}
function pause(){running=false;clearTimeout(timer);lock();}
function act(action,data={}){queue=queue.then(()=>execute(action,data));return queue;}
async function execute(action,data){
  busy=true;lock();$('error').hidden=true;$('status').textContent=action==='load'?'Starting firmware…':'Executing…';
  try{
    const response=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-XT660-Token':token},body:JSON.stringify({action,...data})});
    const state=await response.json();if(!response.ok)throw Error(state.error);render(state);
    $('status').textContent=action==='verify'?'Firmware matches the registered BIN.':'Firmware loaded · simulation only';
  }catch(error){pause();$('error').textContent=error.message;$('error').hidden=false;$('status').textContent='Stopped — check the error.';}
  finally{busy=false;lock();}
}
async function tick(){if(!running)return;await act('step');if(running)timer=setTimeout(tick,100);}
$('load').onclick=()=>act('load',{image:$('image').value});$('step').onclick=()=>act('step');
$('run').onclick=()=>{if(running)pause();else{running=true;lock();tick();}};
$('pitch').oninput=()=>$('pitchLabel').textContent=$('pitch').value+' ticks';
$('crank').onclick=()=>act('crank',{pitch:Number($('pitch').value)});$('stopCrank').onclick=()=>act('stop-crank');
for(const id of ['authenticate','meter','verify'])$(id).onclick=()=>act(id);
function theme(value){document.documentElement.dataset.theme=value;$('theme').textContent=value==='dark'?'Light mode':'Dark mode';try{localStorage.setItem('xt660-emulator-theme',value);}catch{}}
$('theme').onclick=()=>theme(document.documentElement.dataset.theme==='dark'?'light':'dark');
try{theme(localStorage.getItem('xt660-emulator-theme')||'dark');}catch{}
fetch('/api/state').then(r=>r.json()).then(s=>{render(s);if(s.loaded)$('status').textContent='Firmware loaded · simulation paused';}).catch(e=>{$('error').hidden=false;$('error').textContent=e.message;});
window.addEventListener('pagehide',pause);
