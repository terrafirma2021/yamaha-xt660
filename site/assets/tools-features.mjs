import {baseAddress} from './tools-core.mjs';
import {speedState,speedAddresses} from './tools-speed.mjs';

// CPU addresses, never file offsets. These recipes are limited to registered
// images, with the instruction-path checks in test_feature_patches.py.
const families = {
  early: {immo:0x4E7D,pair:[0x9D5A,0xBAC3],mask:2,cut:[[0x765D,[0xF6,0x08,0xF4],[0x06,0x77,0x7A]],[0x778D,[0xF6,0x09,0x00],[0x06,0x77,0xA2]]],legacyCut:[[0x348A,144]],stand:[0xCC5E,0x4E6C],lean:0x4E91},
  late: {immo:0x4619,pair:[0x91EF,0xA465],mask:1,cut:[[0x6E6B,[0xF6,0x09,0x14],[0x06,0x6F,0x8F]],[0x6FA2,[0xF6,0x09,0x20],[0x06,0x6F,0xB7]]],legacyCut:[[0x3451,125],[0x3456,133]],stand:[0xC2C4,0x4608],lean:0x462D}
};
export function featureDefinitions(identity){
  const f=families[identity?.code_family];
  const available=f ? [
    {id:'pair',name:'PAIR valve',detail:'Normal and diagnostic air-induction commands. Enabled means firmware control is available, not that the valve is currently open.',bytes:f.pair.map(address=>({address,on:0x4C,off:0x4D})),guards:f.pair.flatMap(address=>[[address+1,0xF0],[address+2,f.mask]])},
    {id:'immo',name:'Immobilizer',detail:'Authentication configuration read by startup and runtime code. Detected from the bytes, including existing immobilizer-off BINs.',bytes:[{address:f.immo,on:0,off:0x80}],guards:[]},
    {id:'overrun',name:'Overrun cut',detail:'Disabling bypasses the overrun routine and restores its normal fuel multiplier. Sensor thresholds, shared throttle state and rev-limit cuts remain unchanged.',bytes:f.cut.flatMap(([address,on,off])=>on.map((v,i)=>({address:address+i,on:v,off:off[i]}))),legacy:f.legacyCut.map(([address,on])=>({address,on,off:0xFF})),guards:[]}
  ] : ['pair','immo','overrun'].map((id,i)=>({id,name:['PAIR valve','Immobilizer','Overrun cut'][i],detail:''}));
  const o2={id:'o2',name:'O2 sensor / feedback',detail:''};
  if(identity?.code_family==='late')Object.assign(o2,{
    detail:'Disabling stops O2 feedback and new faults 24, 31 and 32. Normal fuel maps remain selected. Existing stored faults are retained.',
    bytes:[{address:0x368E,on:0x80,off:0}],guards:[[0x6410,0xF6],[0x6411,0x36],[0x6412,0x8E],[0x9800,0xF6],[0x9801,0x36],[0x9802,0x8E]]
  });
  else if(identity?.code_family==='early')Object.assign(o2,{detail:'Not configured in this BIN; no O2 enable/disable patch is offered for this application.',readonly:true,
    guards:[[0x18D3,9],...Array.from({length:100},(_,i)=>[0x35B0+i,0]),...Array.from({length:100},(_,i)=>[0x363C+i,0])]});
  const interlocks=f ? [
    {id:'sidestand',name:'Sidestand cut-off',detail:'Disabling allows the ECU to run with the stand down and suppresses new fault 19. The external starter-relay interlock still applies.',bytes:[{address:f.stand[0],on:0x1C,off:0x1D},{address:f.stand[1],on:0,off:0x80}],guards:[[f.stand[0]+1,8],[f.stand[0]+2,0x8C],[f.stand[0]+3,0x80]]},
    {id:'lean-angle',name:'Lean-angle cut-off',detail:'Disabling removes ECU tip-over detection and the sensor fault-41 path: the engine may keep running after a fall. Existing latches or stored faults can still inhibit starting.',bytes:[{address:f.lean,on:0,off:0x80}],guards:[]}
  ] : ['sidestand','lean-angle'].map((id,i)=>({id,name:['Sidestand cut-off','Lean-angle cut-off'][i],detail:''}));
  return [...available,o2,...interlocks];
}
export function featureStates(bytes,identity){
  const base=bytes?baseAddress(bytes):0;
  return featureDefinitions(identity).map(f=>{
    let state='unverified',legacyPatch=false;
    if(bytes&&f.guards?.every(([a,v])=>bytes[a-base]===v)){
      if(f.readonly)state='disabled';
      else {
        const stockThresholds=!f.legacy||f.legacy.every(p=>bytes[p.address-base]===p.on);
        const originalCode=f.bytes.every(p=>bytes[p.address-base]===p.on);
        if(originalCode&&stockThresholds)state='enabled';
        else if(stockThresholds&&f.bytes.every(p=>bytes[p.address-base]===p.off))state='disabled';
        else if(originalCode&&f.legacy?.every(p=>bytes[p.address-base]===p.off)){state='disabled';legacyPatch=true;}
      }
    }
    return {...f,legacyPatch,detail:legacyPatch?'Earlier threshold-based disable detected. Select Disabled to replace it with the targeted bypass, or Enabled to restore stock.':f.readonly&&state==='unverified'?'Configuration changed; no supported O2 patch for this application.':f.detail,state,editable:!!f.bytes&&state!=='unverified'};
  });
}
export function setFeature(bytes,identity,id,enabled){
  if(typeof enabled!=='boolean')throw Error('Feature state must be true or false');
  const f=featureStates(bytes,identity).find(f=>f.id===id);
  if(!f?.editable)throw Error('Feature bytes or firmware are unverified; nothing changed');
  const base=baseAddress(bytes),changes=[...f.bytes.map(p=>({address:p.address,before:bytes[p.address-base],after:enabled?p.on:p.off})),...(f.legacy||[]).map(p=>({address:p.address,before:bytes[p.address-base],after:p.on}))];
  for(const c of changes)bytes[c.address-base]=c.after;
  return {kind:'feature',feature:id,changes:changes.filter(c=>c.before!==c.after)};
}
export function matchesFeatureVariant(bytes,reference,identity){
  if(bytes.length!==reference.length||!families[identity?.code_family])return false;
  const states=featureStates(bytes,identity),base=baseAddress(bytes);
  if(states.some(f=>f.bytes&&!f.editable)||!speedState(bytes,identity).editable)return false;
  const allowed=new Set([0xF7FC,0xF7FD,...speedAddresses(identity),...states.flatMap(f=>[...(f.bytes||[]),...(f.legacy||[])].map(p=>p.address))]);
  return bytes.every((v,i)=>v===reference[i]||allowed.has(i+base));
}
