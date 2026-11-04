// SPDX-License-Identifier: GPL-2.0-or-later
// Owns the MCU and clock. Dashboard messages never drive the execution loop.
import createCore from './xt660.mjs';
let core,cached,paused=true,timer=null,anchor=0,anchorCycles=0,lastLoop=0,lastPublish=0,error='';
let ratio=0,behind=0,suspensions=0;
const call=(name,data)=>{
 const value=JSON.parse(core.ccall(name,'string',data===undefined?[]:['string'],data===undefined?[]:[JSON.stringify(data)]));
 if(value?.error)throw Error(value.error);return value;
};
function reanchor(){anchor=performance.now();anchorCycles=core._xt_cycles();ratio=behind=0;lastLoop=anchor;}
function snapshot(){
 cached=call('xt_state');cached.error=error;
 cached.runtime={wasm:true,independent:true,paused,clock_hz:16000000,realtime_ratio:ratio,behind_ms:behind,
   timing_profile:'Nominal 16 MHz; physical oscillator unconfirmed',browser_suspensions:suspensions};
 lastPublish=performance.now();return cached;
}
function publish(){postMessage({type:'state',state:snapshot()});}
function schedule(){clearTimeout(timer);timer=null;if(!paused&&cached.bike.powered)timer=setTimeout(run,0);}
function run(){
 if(paused||!cached.bike.powered)return;
 try{
  const now=performance.now();
  // A frozen tab resumes from its last simulated instruction. Do not invent
  // the missed engine time or spend minutes running a catch-up burst.
  if(now-lastLoop>2000){++suspensions;reanchor();}
  lastLoop=now;
  const due=anchor+(core._xt_cycles()-anchorCycles)/16000;
  if(due>now+1){timer=setTimeout(run,Math.min(100,due-now));return;}
  call('xt_tick');
  const wall=performance.now()-anchor,sim=(core._xt_cycles()-anchorCycles)/16000;
  ratio=wall>500?sim/wall:0;behind=Math.max(0,wall-sim);
  if(performance.now()-lastPublish>=80)publish();
  timer=setTimeout(run,Math.max(0,anchor+sim-performance.now()));
 }catch(e){error=e.message;paused=true;publish();}
}
async function action(data){
 const a=data.action;
 if(a==='pause'){
  if(typeof data.paused!=='boolean')throw Error('Expected a boolean');paused=data.paused;reanchor();
 }else{
  if(a==='tick'&&!paused)throw Error('Pause before single stepping');
  const result=call('xt_action',data);
  if(a==='trace-export'||a==='storage-export')return result;
  if(a==='load'){paused=true;error='';reanchor();}
  if(a==='key'){paused=!data.enabled;error='';reanchor();}
  if(a==='diagnostics'){paused=false;error='';reanchor();}
  if(a==='start'&&paused){paused=false;reanchor();}
  if(a==='tick')reanchor();
 }
 const s=snapshot();schedule();return s;
}
const ready=createCore({print:()=>{},printErr:message=>console.warn(message)}).then(value=>{
 core=value;call('xt_init');reanchor();publish();postMessage({type:'ready'});
}).catch(e=>{error=e.message;postMessage({type:'fatal',error});throw e;});
let queue=Promise.resolve();
onmessage=event=>{
 const {id,type,data}=event.data;
 queue=queue.then(async()=>{
  try{await ready;const result=type==='state'?cached:await action(data);postMessage({id,result});}
  catch(e){postMessage({id,error:e.message});}
 });
};
