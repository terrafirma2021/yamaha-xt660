import {baseAddress} from './tools-core.mjs';

// Fixed pulses per dashboard reply, NOT percent or km/h. No persistent RAM.
// See SPEED_OUTPUT.md and test_speed_patch.py for placement and byte execution.
export const speedLayouts = {
  early:{hook:0x6341,raw:0x0AE3,output:0x08A7,cave:0x4FA6},
  late:{hook:0x5B03,raw:0x0B06,output:0x08A9,cave:0xB100}
};
const word=n=>[n>>8,n&255];
export function speedRecipe(identity,enabled,offset){
  const f=speedLayouts[identity?.code_family];
  if(!f||typeof enabled!=='boolean'||!Number.isInteger(offset)||offset< -20||offset>20)throw Error('Speed output requires a supported BIN and a whole pulse offset from -20 to +20');
  const block=Array(24).fill(255),stock=enabled&&offset===0;
  if(!stock){
    // PSHC; LDAA raw; BEQ done; ADDA #offset; BCC/BCS done;
    // LDAA #upper/lower bound; done: PULC; RTS.
    // Caller STAA restores N/Z/V for the returned A; C and mask bits survive.
    const code=enabled?[0x39,0xB6,...word(f.raw),0x27,6,0x8B,offset&255,offset<0?0x25:0x24,2,0x86,offset<0?0:255,0x38,0x3D]:[0x39,0x86,0,0x38,0x3D];
    block.splice(0,code.length,...code);
    block.splice(16,6,0x56,0x53,0x53,1,offset+20,Number(enabled));
  }
  return [{address:f.hook,bytes:stock?[0xB6,...word(f.raw)]:[0x16,...word(f.cave)]},{address:f.cave,bytes:block}];
}
export function speedAddresses(identity){const f=speedLayouts[identity?.code_family];return f?[...Array.from({length:3},(_,i)=>f.hook+i),...Array.from({length:24},(_,i)=>f.cave+i)]:[]}
export function speedState(bytes,identity){
  const f=speedLayouts[identity?.code_family],bad={editable:false,enabled:null,offset:null};
  if(!bytes||!f)return bad;
  const base=baseAddress(bytes),equals=(a,expected)=>expected.every((v,i)=>bytes[a-base+i]===v);
  if(!equals(f.hook+3,[0x7A,...word(f.output)]))return bad;
  let enabled=true,offset=0;
  if(!equals(f.cave,Array(24).fill(255))){
    if(!equals(f.cave+16,[0x56,0x53,0x53,1]))return bad;
    offset=bytes[f.cave+20-base]-20;
    const flag=bytes[f.cave+21-base];
    if(flag>1||offset< -20||offset>20)return bad;
    enabled=!!flag;
  }
  if(!speedRecipe(identity,enabled,offset).every(p=>equals(p.address,p.bytes)))return bad;
  return {editable:true,enabled,offset};
}
export function setSpeed(bytes,identity,enabled,offset){
  if(!speedState(bytes,identity).editable)throw Error('Speed patch bytes are unverified; nothing changed');
  const recipe=speedRecipe(identity,enabled,offset),base=baseAddress(bytes),changes=[];
  for(const p of recipe)for(const [i,after] of p.bytes.entries()){
    const address=p.address+i,before=bytes[address-base];
    if(before!==after)changes.push({address,before,after});
  }
  for(const c of changes)bytes[c.address-base]=c.after;
  return {kind:'feature',feature:'speed-output',changes};
}
