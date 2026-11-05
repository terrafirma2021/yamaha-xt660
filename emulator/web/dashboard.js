 'use strict';
const $=id=>document.getElementById(id),token=document.querySelector('meta[name=session]').content;
const transport=window.XT660Transport??{
 async state(){const r=await fetch('/api/state');if(!r.ok)throw Error('Runtime unavailable');return r.json();},
 async action(action,data){const r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-XT660-Token':token},body:JSON.stringify({action,...data})});const s=await r.json();if(!r.ok)throw Error(s.error);return s;}
};
const bench=document.querySelector('.advanced');
let state=null,busy=false,pendingActions=0,paused=false,timer=null,queue=Promise.resolve(),ticking=false;
function text(id,value){const element=$(id),next=String(value);if(element.textContent!==next)element.textContent=next;}
const names=['Throttle','Intake pressure','O₂ input','Intake temperature','Supply monitor','Lean sensor','Coolant','Auxiliary'];
for(let n=0;n<40;n++)$('tach').append(document.createElement('i'));
for(let n=0;n<8;n++){
 const row=document.createElement('div');row.className='sensor';
 const label=document.createElement('label');label.htmlFor='adc'+n;label.textContent=n===0?'Throttle control (%)':names[n]+' (ADC)';
 const slider=document.createElement('input');Object.assign(slider,{id:'adc'+n,type:'range',min:0,max:n===0?100:1023,value:n===0?0:512,disabled:true});slider.setAttribute('aria-label',n===0?'Throttle control percent':names[n]+' ADC');
 const value=document.createElement('input');Object.assign(value,{id:'value'+n,type:'number',min:0,max:n===0?100:1023,value:n===0?0:512,disabled:true});value.setAttribute('aria-label',n===0?'Throttle control percent value':names[n]+' raw value');
 if(n===0)row.title='Control travel: 0% closed / 100% open. Nominal Yamaha d:01 endpoints: 16 / 100. Intermediate sensor travel is simulated.';
 slider.oninput=()=>value.value=slider.value;
 const send=v=>n===0?control('throttle',v):n===6?control('coolant',v):act('adc',{channel:n,value:v});
 slider.onchange=()=>send(Number(slider.value));value.onchange=()=>value.checkValidity()?send(Number(value.value)):value.reportValidity();
 row.append(label,slider,value);$('sensors').append(row);
}
function lock(){
 const b=state?.bike,powered=!!b?.powered;
 $('load').disabled=busy;$('image').disabled=busy;$('key').disabled=busy||!b?.selected;
 for(const id of ['runSwitch','neutral','inGear','throttle','releaseThrottle','faultSelect','nextFault','restore','coolantNormal','coolantHot','pause','step','verify'])$(id).disabled=!powered;
 for(const button of document.querySelectorAll('[data-gear]'))button.disabled=!powered||(!b?.models&&Number(button.dataset.gear)>1);
 $('model').disabled=busy||powered||!b?.selected||!b?.models||b.models.length<2;
 $('starter').disabled=!powered||!b.run||b.rotating||b.starting||b.authentication==='Key rejected'||busy;
 $('step').disabled||=!paused||busy;$('verify').disabled||=busy;
 for(let n=0;n<8;n++)for(const prefix of ['adc','value'])$(prefix+n).disabled=!powered;
 $('wrongKey').disabled=powered;
 const diag=b?.meter.mode==='diagnostic';
 $('diagnostics').disabled=!b?.selected||busy;
 for(const id of ['diagPrev','diagNext','history','count'])$(id).disabled=!diag||busy;
 $('clearHistory').disabled=!diag||b?.meter.diagnostic_id!==62||busy;
 const actuator=diag&&b?.meter.diagnostic_kind==='actuator';
 $('runTest').hidden=$('stopTest').hidden=!actuator;
 $('runTest').disabled=!actuator||busy;$('stopTest').disabled=!actuator||!b?.run||busy;
 $('clearHistory').hidden=!diag||b?.meter.diagnostic_id!==62;
 $('starter').disabled||=b?.meter.mode!=='normal';
 for(const id of ['traceLink','storageLink'])$(id).setAttribute('aria-disabled',String(!powered||busy));
}
function wave(trace){
  const svg=$('wave'),ns='http://www.w3.org/2000/svg';svg.replaceChildren();
  const rows=trace.filter(e=>e.kind==='output'&&[3,6].includes(e.channel));
  if(!rows.length){const text=document.createElementNS(ns,'text');text.setAttribute('x',24);text.setAttribute('y',80);text.textContent='No output transitions in this trace window.';svg.append(text);return;}
  const start=rows[0].cycle,end=rows.at(-1).cycle,span=Math.max(1,end-start),x=t=>20+(t-start)*600/span;
  for(const [idx,ch] of [3,6].entries()){
    const events=rows.filter(e=>e.channel===ch),base=45+idx*45;
    const line=document.createElementNS(ns,'line');for(const [k,v] of Object.entries({x1:20,x2:620,y1:base,y2:base}))line.setAttribute(k,v);svg.append(line);
    if(!events.length)continue;
    let level=1-events[0].value,d=`M20 ${base-level*25}`;
    for(const e of events){d+=` H${x(e.cycle)} V${base-e.value*25}`;level=e.value;}d+=' H620';
    const path=document.createElementNS(ns,'path');path.setAttribute('d',d);path.setAttribute('stroke',['var(--coil)','var(--injector)','var(--secondary)'][idx]);svg.append(path);
  }
}

function renderBench(s){
 text('serial',s.transcript?.length?s.transcript.map(r=>'TX '+r.request+'  →  RX '+r.reply).join('\n'):'No replies.');
 $('serial').scrollTop=$('serial').scrollHeight;
 text('cycles',(s.counts?.bus_cycles??0).toLocaleString());wave(s.trace??[]);
}
bench.addEventListener('toggle',()=>{if(bench.open&&state)renderBench(state);});

function render(s){
 const previousSelected=state?.bike.selected;
 state=s;if(s.runtime?.independent)paused=s.runtime.paused;
 const b=s.bike,m=b.meter,powered=b.powered;
 if(!$('image').options.length)for(const v of s.images){const o=document.createElement('option');o.value=v.id;o.textContent=v.label;$('image').append(o);}
 if(b.selected&&b.selected!==previousSelected)$('image').value=b.selected;
 const models=b.models??['xt660x'];
 if([...$('model').options].map(o=>o.value).join(',')!==models.join(',')){
  $('model').replaceChildren(...models.map(id=>{const o=document.createElement('option');o.value=id;o.textContent=id.toUpperCase();return o;}));
 }
 $('model').value=b.model??'xt660x';
 $('model').title=powered?'Turn the key off to change motorcycle':'Stock gearing and tyre circumference';
 if(!$('faultSelect').options.length)for(const v of b.faults){const o=document.createElement('option');o.value=v.id;o.textContent=v.label;$('faultSelect').append(o);}
 if(document.activeElement!==$('faultSelect'))$('faultSelect').value=b.fault;
 $('display').classList.toggle('off',!powered);
 $('key').setAttribute('aria-pressed',String(powered));$('key').setAttribute('aria-label','Turn ignition key '+(powered?'off':'on'));text('keyLabel',powered?'KEY ON':'KEY OFF');
 $('runSwitch').setAttribute('aria-pressed',String(b.run));text('runLabel',b.run?'ON':'STOP');
 $('key').title='Turn ignition key '+(powered?'off':'on');
 $('runSwitch').setAttribute('aria-label','Engine run switch: '+(b.run?'on, lower end pressed':'stop, upper end pressed'));$('runSwitch').title=b.run?'Run · lower end pressed. Click to stop':'Stop · upper end pressed. Click to run';
 $('starter').setAttribute('aria-pressed',String(b.starting));
 for(const button of document.querySelectorAll('[data-gear]'))button.setAttribute('aria-pressed',String(Number(button.dataset.gear)===b.gear));
 $('gear').textContent=powered?(b.gear||'N'):'—';$('gear').parentElement.classList.toggle('engaged',!!b.gear);
 $('gear').title='Selected simulated gear; the ECU receives neutral and VSS inputs, not a gear-number message';
 if(document.activeElement!==$('throttle'))$('throttle').value=b.throttle;$('throttleValue').textContent=b.throttle+'%';
 $('auth').textContent=b.authentication;$('frames').textContent=m.frames;
 $('engineState').textContent=!powered?'IGNITION OFF':!b.run?'ENGINE STOP':b.starting?'STARTING':b.rotating?'ENGINE RUNNING':'ENGINE STOPPED';
 $('sessionHint').textContent=!powered?'Key on. Run on. Press start.':b.authentication==='Key rejected'?'Key rejected. Cycle ignition to try again.':b.starting?'Cranking. Waiting for ECU outputs.':b.rotating?'Engine running. Open the throttle.':'Press start when you’re ready.';
 text('simState',powered?(paused?'Paused':'Running'):'Stopped');text('pause',paused?'Resume simulation':'Pause simulation');
 if(s.runtime?.independent&&powered&&!paused)text('simState',s.runtime.realtime_ratio?(s.runtime.behind_ms>150?'Below real time · ':'Real time · ')+s.runtime.realtime_ratio.toFixed(2)+'×':'Running');
 $('sessionLight').classList.toggle('on',powered&&!paused);text('link',!powered?'KEY OFF':m.connected?(paused?'K-LINE / PAUSED':'K-LINE / CONNECTED'):'WAITING FOR ECU');
 $('heartbeat').classList.toggle('active',m.connected&&m.frames%2===0);
 $('speed').textContent=m.connected&&Number.isFinite(m.speed_mph)?Math.round(m.speed_mph):'—';
 $('speed').title='Received VSS pulses / elapsed simulated time, stock tyre and gearing. Assumed 20 pulses per output-shaft turn; MPH remains an estimate.';
 $('speedLabel').textContent='MPH · EST.';$('rpmLabel').textContent='RPM · NOMINAL';
 $('rpm').textContent=m.connected?Math.round(m.engine_code*190/5.12).toLocaleString():'—';
 $('rpm').title='Received engine code × 190 / 5.12, nominal 16 MHz profile';
 for(const [i,bar] of [...$('tach').children].entries())bar.classList.toggle('active',m.connected&&i<m.engine_code*190/5.12/200);
 $('temperature').textContent=m.connected?($('celsius').checked?'~'+(m.coolant_code-30):m.coolant_code):'—';$('temperatureUnit').textContent=$('celsius').checked?'°C EST.':'CODE';
 $('hotLamp').classList.toggle('hot',m.connected&&m.coolant_code>=136);$('hotLamp').title='Dash warning threshold: received coolant code ≥ 136';
 $('faultLamp').classList.toggle('on',!!m.warning);
 $('faultText').textContent=!powered?'Turn the key to connect':!m.connected?'Waiting for a valid meter reply':m.fault?'FAULT '+m.fault+' · '+m.fault_name:m.warning?'ECU warning lamp on':'No active fault code';
 $('faultText').classList.toggle('alert',!!m.fault);
 const diag=m.mode!=='normal';
 $('display').classList.toggle('diagnostic',diag);
 $('sessionTitle').textContent=diag?'Diagnostics':'Engine';
 text('diagnostics',diag?'Exit diagnostics':'Enter diagnostics');$('diagControls').hidden=!diag;
 const entryText=m.mode==='hold-confirm'?'Confirm dIAG · holding SELECT + RESET':m.mode==='menu-ready'?'dIAG selected · releasing buttons':'Key on · holding SELECT + RESET';
 $('diagState').textContent=m.mode==='diagnostic'?'d:'+String(m.diagnostic_id??'—')+' · '+String(m.diagnostic_value??'—'):entryText+' · '+m.entry_seconds+' s simulated';
 $('diagNumber').textContent=m.diagnostic_id==null?'d:—':'d:'+String(m.diagnostic_id).padStart(2,'0');$('diagName').textContent=m.diagnostic_name;$('diagValue').textContent=m.diagnostic_value??'—';
 $('diagHelp').textContent=m.mode!=='diagnostic'?'Entry and confirmation are automatic. The ECU advances its own hold counters.':m.diagnostic_kind==='actuator'?'Run test cycles the simulated run switch. The ECU controls the output pulses and warning lamp.':m.diagnostic_kind==='erase'?'Clear history performs the run-switch sequence. Active faults may remain.':m.diagnostic_kind==='history'?(m.diagnostic_id===63?'The ECU cycles active oxygen-sensor fault codes.':'The ECU cycles stored fault codes automatically.'):'Previous and Next send the dashboard button commands. Values come from the ECU.';
 if(diag){$('speed').textContent=m.mode==='diagnostic'?$('diagNumber').textContent:'dIAG';$('speed').title='Diagnostic number returned by the ECU';$('rpm').textContent=m.diagnostic_value??'—';$('speedLabel').textContent='DIAGNOSTIC';$('rpmLabel').textContent='ECU REPLY';$('rpm').title='Diagnostic data byte returned by the ECU';$('temperature').textContent='—';$('hotLamp').classList.remove('hot');$('faultText').textContent=m.mode==='diagnostic'?m.diagnostic_name:$('diagState').textContent;$('sessionHint').textContent=m.mode==='diagnostic'?'Use the dash buttons to select a diagnostic item.':'Waiting for the ECU’s diagnostic hold sequence.';}
 $('faultHistory').textContent=m.seen.length?'Codes received this key cycle: '+m.seen.join(', '):'No fault codes received.';
 if(bench.open)renderBench(s);
 if(s.adc)for(let n=0;n<8;n++)for(const prefix of ['adc','value'])if(document.activeElement!==$(prefix+n))$(prefix+n).value=n===0?b.throttle:s.adc[n];
 text('status',!b.selected?'Choose an ECU, then turn the key.':!powered?'ECU selected · key off':paused?'Simulation paused':'ECU running · dash connected via SCI1');
 if(s.error){text('error',s.error);$('error').hidden=false;}
 lock();
}
function act(action,data={},background=false){
 // Background polling shares the request queue without dimming the controls.
 // Lock foreground commands as soon as they are queued, including while a
 // poll is finishing, so repeated clicks cannot enqueue duplicate operations.
 if(!background){pendingActions++;busy=true;lock();}
 queue=queue.then(()=>execute(action,data,background));return queue;
}
async function execute(action,data,background){
 try{const s=await transport.action(action,data);render(s);$('error').hidden=!!s.error?false:true;if(action==='verify')$('status').textContent='All flash bytes match the registered BIN.';return true;}
 catch(e){if(!state?.runtime?.independent){paused=true;clearTimeout(timer);}$('error').textContent=e.message;$('error').hidden=false;return false;}
 finally{if(!background)busy=--pendingActions>0;lock();}
}
async function tick(){
 if(state?.runtime?.independent){
  // Snapshot reads never step or pace the MCU. The worker owns execution.
  if(ticking)return;ticking=true;
  queue=queue.then(async()=>{
   try{render(await transport.state());}
   catch(e){text('error',e.message);$('error').hidden=false;}
  });
  await queue;ticking=false;timer=setTimeout(tick,50);return;
 }
 if(paused||!state?.bike.powered||ticking)return;
 ticking=true;
 const started=performance.now(),cycles=state.counts?.bus_cycles??0;
 await act('tick',{},true);ticking=false;
 // Pace against the existing nominal 16 MHz profile. If execution already
 // took longer, do not add the old fixed 80 ms pause to every batch.
 const simulatedMs=Math.max(0,((state.counts?.bus_cycles??cycles)-cycles)/16000);
 if(!paused&&state?.bike.powered)timer=setTimeout(tick,Math.max(0,simulatedMs-(performance.now()-started)));
}
function resume(){if(state?.runtime?.independent){if(paused)act('pause',{paused:false});return;}paused=false;clearTimeout(timer);if(state)render(state);tick();}
function pause(){if(state?.runtime?.independent){if(!paused)act('pause',{paused:true});return;}paused=true;clearTimeout(timer);if(state)render(state);}
const control=(name,value)=>act('control',{name,value});
$('load').onclick=async()=>{const image=$('image').value;if(!state?.runtime?.independent)pause();await act('load',{image});};
$('key').onclick=async()=>{const enabled=!state.bike.powered;if(!state.runtime?.independent)pause();$('key').dataset.turning=enabled?'on':'off';try{if(await act('key',{enabled,wrong_key:$('wrongKey').checked}))if(enabled)resume();}finally{delete $('key').dataset.turning;}};
$('runSwitch').onclick=async event=>{
 if(busy)return;
 const button=$('runSwitch');let enabled=!state.bike.run;
 if(event.detail){
  // Project the pointer onto the rocker's local long axis, including its photo rotation.
  const box=button.getBoundingClientRect(),matrix=new DOMMatrix(getComputedStyle(button).transform);
  const along=(event.clientX-box.x-box.width/2)*matrix.c+(event.clientY-box.y-box.height/2)*matrix.d;
  if(Math.abs(along)>button.offsetHeight*.15)enabled=along>0;
 }
 if(enabled===state.bike.run)return;
 button.dataset.turning=enabled?'run':'stop';
 try{await control('run',enabled);}finally{delete button.dataset.turning;}
};
$('starter').onclick=async()=>{if(await act('start'))resume();};
for(const button of document.querySelectorAll('[data-gear]'))button.onclick=()=>control('gear',Number(button.dataset.gear));
$('model').onchange=()=>control('model',$('model').value);
$('throttle').oninput=()=>$('throttleValue').textContent=$('throttle').value+'%';$('throttle').onchange=()=>control('throttle',Number($('throttle').value));
$('releaseThrottle').onclick=()=>control('throttle',0);
$('faultSelect').onchange=()=>control('fault',$('faultSelect').value);
$('nextFault').onclick=()=>{const options=state.bike.faults;control('fault',options[(options.findIndex(x=>x.id===state.bike.fault)+1)%options.length].id);};
$('restore').onclick=()=>control('fault','none');$('coolantNormal').onclick=()=>control('coolant',512);$('coolantHot').onclick=()=>control('coolant',80);
$('pause').onclick=()=>paused?resume():pause();$('step').onclick=()=>act('tick');$('verify').onclick=()=>act('verify');
$('celsius').onchange=()=>render(state);
 $('diagnostics').onclick=async()=>{if(!state.runtime?.independent)pause();if(await act('diagnostics',{enabled:state.bike.meter.mode==='normal'}))resume();};
 $('diagPrev').onclick=()=>act('diagnostic-next',{direction:-1});$('diagNext').onclick=()=>act('diagnostic-next',{direction:1});
 $('history').onclick=()=>act('diagnostic-item',{number:61});$('count').onclick=()=>act('diagnostic-item',{number:62});
 $('clearHistory').onclick=()=>act('clear-history');
 $('runTest').onclick=async()=>{if(await act('diagnostic-test',{enabled:true}))resume();};
 $('stopTest').onclick=()=>act('diagnostic-test',{enabled:false});
function theme(v){document.documentElement.dataset.theme=v;$('theme').textContent=v==='dark'?'Light mode':'Dark mode';try{localStorage.setItem('xt660-emulator-theme',v);}catch{}}
$('theme').onclick=()=>theme(document.documentElement.dataset.theme==='dark'?'light':'dark');try{theme(localStorage.getItem('xt660-emulator-theme')||'dark');}catch{}
transport.state().then(s=>{paused=true;render(s);if(s.runtime?.independent)tick();}).catch(e=>{$('error').hidden=false;$('error').textContent=e.message;});
window.addEventListener('pagehide',()=>{if(state?.runtime?.independent)clearTimeout(timer);else pause();});
window.addEventListener('pageshow',e=>{if(e.persisted&&state?.runtime?.independent){clearTimeout(timer);tick();}});
