import {featureDefinitions,featureStates} from '../../flasher/core/tools-features.mjs';
import {speedRecipe,speedLayouts,speedState} from '../../flasher/core/tools-speed.mjs';

// Native XDFPATCH entries retain both byte sequences. Apply and Remove operate
// on the whole recipe, including branch operands and expected instruction bytes.
export function featurePatches(bytes,identity){
  const patches=[], base=identity.base_address;
  const add=(id,title,description,changes,guards=[],category='Features')=>{
    const cells=new Map();
    for(const [address,value] of guards)cells.set(address,{address,before:value,after:value});
    for(const p of changes)cells.set(p.address,p);
    const entries=[];
    for(const p of [...cells.values()].sort((a,b)=>a.address-b.address)){
      if(p.address<base||p.address>=base+bytes.length)throw Error('Patch outside BIN');
      const last=entries.at(-1);
      if(last&&last.address+last.before.length===p.address-base){last.before.push(p.before);last.after.push(p.after);}
      else entries.push({address:p.address-base,before:[p.before],after:[p.after]});
    }
    patches.push({id,title,description,category,entries});
  };
  for(const f of featureStates(bytes,identity)){
    if(!f.bytes)continue; // Early O2 is not a supported switch.
    if(!f.editable||f.legacyPatch)throw Error('Unrecognised feature state: '+identity.id+'/'+f.id);
    const override=f.id==='co-range';
    add(f.id,override?f.name:'Disable '+f.name,
      `${f.detail||'Keeps dashboard CO correction at full strength across the running range.'} Apply = ${override?'override enabled':'disabled'}; Remove = ${override?'stock fade-out':'enabled'}. Use the whole patch, not individual entries. Correct the startup checksum after saving. Code-checked; hardware operation has not been validated.`,
      f.bytes.map(p=>({address:p.address,before:override?p.off:p.on,after:override?p.on:p.off})),
      [...f.guards,...(f.legacy||[]).map(p=>[p.address,p.on])]);
  }
  if(!speedState(bytes,identity).editable)throw Error('Unrecognised speed code');
  const stock=speedRecipe(identity,true,0),layout=speedLayouts[identity.code_family];
  for(const offset of [null,...Array.from({length:41},(_,i)=>i-20).filter(n=>n!==0)]){
    const target=speedRecipe(identity,offset!==null,offset||0);
    add(offset===null?'speed-disable':'speed-offset-'+offset,offset===null?'Speedo disable':`Pulse offset ${offset>0?'+':''}${offset}`,
      'Apply one speed patch at a time; Remove it before selecting another. Zero remains zero; output is clamped to 0–255 pulses per reply. This changes dashboard speed and distance reporting only. Correct the startup checksum after saving. Code-checked; hardware operation has not been validated.',
      stock.flatMap((p,j)=>p.bytes.map((v,i)=>({address:p.address+i,before:v,after:target[j].bytes[i]}))),
      [[layout.hook+3,0x7A],[layout.hook+4,layout.output>>8],[layout.hook+5,layout.output&255]],offset===null?'Features':'Speed pulse offset');
  }
  return patches;
}
