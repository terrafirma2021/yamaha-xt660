import {baseAddress} from './tools-core.mjs';

// CPU addresses, never file offsets. These recipes are limited to registered
// images, with the instruction-path checks in test_feature_patches.py.
const families = {
  early: {immo:0x4E7D,pair:[0x9D5A,0xBAC3],mask:2,cut:[[0x348A,144]]},
  late: {immo:0x4619,pair:[0x91EF,0xA465],mask:1,cut:[[0x3451,125],[0x3456,133]]}
};
export function featureDefinitions(identity){
  const f=families[identity?.code_family];
  const available=f ? [
    {id:'pair',name:'PAIR valve',detail:'Normal and diagnostic air-induction commands. Enabled means firmware control is available, not that the valve is currently open.',bytes:f.pair.map(address=>({address,on:0x4C,off:0x4D})),guards:f.pair.flatMap(address=>[[address+1,0xF0],[address+2,f.mask]])},
    {id:'immo',name:'Immobilizer',detail:'Authentication configuration read by startup and runtime code. Detected from the bytes, including existing immobilizer-off BINs.',bytes:[{address:f.immo,on:0,off:0x80}],guards:[]},
    {id:'overrun',name:'Deceleration fuel cut',detail:'Closed-throttle fuel-cut thresholds. Disabling also clears an active deceleration cut and restores its fuel multiplier. Rev-limit and other cut logic are unchanged.',bytes:f.cut.map(([address,on])=>({address,on,off:0xFF})),guards:[]}
  ] : ['pair','immo','overrun'].map((id,i)=>({id,name:['PAIR valve','Immobilizer','Deceleration fuel cut'][i],detail:'Open a registered BIN to identify this feature.'}));
  return [...available,
    {id:'o2',name:'O2 sensor / feedback',detail:'Unverified. The supplied XDF flag has not been traced to a complete feedback and fault disable. No patch is offered.'},
    {id:'spark-overrun',name:'Deceleration spark cut',detail:'Unverified. A separate overrun spark-cut switch has not been established. Ignition corrections and rev-limit spark cuts are not treated as this feature.'}
  ];
}
export function featureStates(bytes,identity){
  const base=bytes?baseAddress(bytes):0;
  return featureDefinitions(identity).map(f=>{
    let state='unverified';
    if(bytes&&f.bytes&&f.guards.every(([a,v])=>bytes[a-base]===v)){
      if(f.bytes.every(p=>bytes[p.address-base]===p.on))state='enabled';
      else if(f.bytes.every(p=>bytes[p.address-base]===p.off))state='disabled';
    }
    return {...f,state,editable:state!=='unverified'};
  });
}
export function setFeature(bytes,identity,id,enabled){
  if(typeof enabled!=='boolean')throw Error('Feature state must be true or false');
  const f=featureStates(bytes,identity).find(f=>f.id===id);
  if(!f?.editable)throw Error('Feature bytes or firmware are unverified; nothing changed');
  const base=baseAddress(bytes),changes=f.bytes.map(p=>({address:p.address,before:bytes[p.address-base],after:enabled?p.on:p.off}));
  for(const c of changes)bytes[c.address-base]=c.after;
  return {kind:'feature',feature:id,changes:changes.filter(c=>c.before!==c.after)};
}
export function matchesFeatureVariant(bytes,reference,identity){
  if(bytes.length!==reference.length||!families[identity?.code_family])return false;
  const states=featureStates(bytes,identity),base=baseAddress(bytes);
  if(states.some(f=>f.bytes&&!f.editable))return false;
  const allowed=new Set([0xF7FC,0xF7FD,...states.flatMap(f=>(f.bytes||[]).map(p=>p.address))]);
  return bytes.every((v,i)=>v===reference[i]||allowed.has(i+base));
}
