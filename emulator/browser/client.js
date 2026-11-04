// SPDX-License-Identifier: GPL-2.0-or-later
// UI adapter: controls and cached worker snapshots, no CPU execution here.
(()=>{
 const pending=new Map();let serial=0,cached,failure;
 let resolveReady,rejectReady;
 const ready=new Promise((resolve,reject)=>{resolveReady=resolve;rejectReady=reject;});
 const worker=new Worker(new URL('worker.js',document.baseURI),{type:'module'});
 function fail(message){failure=Error(message);rejectReady(failure);for(const p of pending.values())p.reject(failure);pending.clear();}
 worker.onerror=e=>fail(e.message||'Browser emulator failed to start');
 worker.onmessage=({data})=>{
  if(data.type==='state'){cached=data.state;return;}
  if(data.type==='ready'){resolveReady();return;}
  if(data.type==='fatal'){fail(data.error);return;}
  const p=pending.get(data.id);if(!p)return;pending.delete(data.id);
  if(data.error)p.reject(Error(data.error));else p.resolve(data.result);
 };
 async function request(type,data){
  await ready;if(failure)throw failure;if(pending.size>=16)throw Error('Control queue is full');
  const id=++serial;return new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});worker.postMessage({id,type,data});});
 }
 window.XT660Transport={
  async state(){await ready;if(failure)throw failure;return cached;},
  async action(action,data={}){const result=await request('action',{action,...data});cached=result;return result;}
 };
 for(const [id,action,name] of [['traceLink','trace-export','xt660-trace.csv'],['storageLink','storage-export','xt660-storage-fixture.bin']]){
  document.getElementById(id).onclick=async event=>{
   event.preventDefault();if(event.currentTarget.getAttribute('aria-disabled')==='true')return;
   try{
    const data=await request('action',{action});
    const content=action==='storage-export'?new Uint8Array(data):'cycle,kind,channel,value,pc\n'+data.map(row=>row.join(',')).join('\n')+'\n';
    const url=URL.createObjectURL(new Blob([content],{type:action==='storage-export'?'application/octet-stream':'text/csv'}));
    const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
   }catch(e){const alert=document.getElementById('error');alert.textContent=e.message;alert.hidden=false;}
  };
 }
})();
