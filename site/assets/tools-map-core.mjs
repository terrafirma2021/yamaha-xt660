import {featureStates,matchesFeatureVariant} from './tools-features.mjs';
import {speedState} from './tools-speed.mjs';
import {readCell,cellOffset,hex,baseAddress} from './tools-core.mjs';
export function mapCategory(m){
 if(m.category)return m.category;const name=(m.display_name||m.id).toLowerCase();
 if(/ignition|spark|dwell/.test(name))return 'Ignition';
 if(/fuel|inject/.test(name))return 'Fuel';
 if(/sensor|conversion/.test(name))return 'Sensors';
 if(/limit|cut|fan/.test(name))return 'Limits & control';
 return 'Corrections & other';
}
export function axisLabel(m,name,i){
  const a=m[name]?.raw_values;
  if(m.kind==='2D_step_grid'&&a)return i===0?'≤'+a[0]:i===a.length?'>'+a.at(-1):a[i-1]+'…'+a[i];
  if(a)return a[i];
  if(name==='column_axis'&&m.kind==='1D_uniform_axis')return Number((m.input_min_raw+i*m.index_divisor/m.index_factor_raw).toFixed(4));
  return i+1;
}
export function rectangle(m,a,b){
  const n=m.rows*m.columns;if(![a,b].every(i=>Number.isInteger(i)&&i>=0&&i<n))throw Error('Selection outside map');
  return {r0:Math.min(Math.floor(a/m.columns),Math.floor(b/m.columns)),r1:Math.max(Math.floor(a/m.columns),Math.floor(b/m.columns)),c0:Math.min(a%m.columns,b%m.columns),c1:Math.max(a%m.columns,b%m.columns)};
}
export function indices(m,s){const out=[];for(let r=s.r0;r<=s.r1;r++)for(let c=s.c0;c<=s.c1;c++)out.push(r*m.columns+c);return out}
export function parseCells(text){
  const rows=text.trim().split(/\r?\n/).map(r=>r.trim().split(/[\t,; ]+/).map(v=>{if(!/^[+-]?\d+$/.test(v))throw Error('Paste whole decimal values separated by tabs, commas or spaces');return Number(v)}));
  if(!text.trim()||rows.some(r=>r.length!==rows[0].length))throw Error('Paste a rectangular block of values');return rows;
}
export function previewEdit(m,values,original,s,operation,value,pasteText=''){
  const max=2**(m.element_bytes*8)-1,out=[],selected=indices(m,s);
  if(['set','add','multiply'].includes(operation)&&!Number.isFinite(value))throw Error('Enter a finite value');
  if(operation==='set'&&!Number.isInteger(value))throw Error('Set value must be a whole raw integer');
  let pasted;if(operation==='paste'){
    pasted=parseCells(pasteText);
    if(s.r0+pasted.length>m.rows||s.c0+pasted[0].length>m.columns)throw Error('Pasted block does not fit from the selection’s top-left cell');
  }
  const candidates=pasted?pasted.flatMap((row,r)=>row.map((v,c)=>[(s.r0+r)*m.columns+s.c0+c,v])):selected.map(i=>{
    const r=Math.floor(i/m.columns),c=i%m.columns;
    let v=values[i];
    if(operation==='set')v=value;
    else if(operation==='add')v+=value;
    else if(operation==='multiply')v*=value;
    else if(operation==='restore')v=original[i];
    else if(operation==='smooth'){
      const neighbours=[];for(let y=Math.max(s.r0,r-1);y<=Math.min(s.r1,r+1);y++)for(let x=Math.max(s.c0,c-1);x<=Math.min(s.c1,c+1);x++)neighbours.push(values[y*m.columns+x]);
      v=neighbours.reduce((a,b)=>a+b,0)/neighbours.length;
    }else if(operation==='horizontal'||operation==='vertical'){
      const horizontal=operation==='horizontal',lo=horizontal?s.c0:s.r0,hi=horizontal?s.c1:s.r1,pos=horizontal?c:r;
      if(lo===hi)throw Error('Interpolation needs at least two '+(horizontal?'columns':'rows'));
      const key=horizontal?'column_axis':'row_axis',coords=Array.from({length:hi-lo+1},(_,k)=>axisLabel(m,key,lo+k));
      const numeric=coords.every(Number.isFinite)&&coords.every((v,k)=>!k||v>coords[k-1]);
      const t=numeric?(coords[pos-lo]-coords[0])/(coords.at(-1)-coords[0]):(pos-lo)/(hi-lo);
      const left=horizontal?values[r*m.columns+lo]:values[lo*m.columns+c],right=horizontal?values[r*m.columns+hi]:values[hi*m.columns+c];v=left+(right-left)*t;
    }else throw Error('Unknown edit operation');
    return [i,v];
  });
  for(const [index,v] of candidates){const after=Math.round(v);if(!Number.isSafeInteger(after)||after<0||after>max)throw Error(`Result outside 0–${max} at row ${Math.floor(index/m.columns)+1}, column ${index%m.columns+1}. No cells changed.`);if(after!==values[index])out.push({index,before:values[index],after})}
  return out;
}
const xml=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
export function exportXdf(bytes,base,maps,identity){
  if(!identity||!maps.length)throw Error('Load a recognised BIN before exporting XDF');
  const categoryNames=[...new Set(maps.map(m=>mapCategory(m)))];
  const tables=maps.map((m,j)=>{
    const address=cellOffset(bytes,base,m,0);readCell(bytes,base,m,m.rows*m.columns-1);
    const axes=[['x','column_axis',m.columns],['y','row_axis',m.rows]].map(([id,key,n])=>`<XDFAXIS id="${id}" uniqueid="0x0"><EMBEDDEDDATA mmedelementsizebits="16" mmedcolcount="${n}"/><units>Raw axis</units><indexcount>${n}</indexcount><decimalpl>4</decimalpl><outputtype>4</outputtype><datatype>0</datatype><unittype>0</unittype><DALINK index="0"/>${Array.from({length:n},(_,i)=>`<LABEL index="${i}" value="${xml(axisLabel(m,key,i))}"/>`).join('')}<MATH equation="X"><VAR id="X"/></MATH></XDFAXIS>`).join('');
    return `<XDFTABLE uniqueid="${hex(j+1)}" flags="0x30"><title>${xml(m.display_name||m.id)}</title><description>${xml(`${m.id}; CPU ${m.data_address}; ${m.confidence||'Recovered layout'}. Raw unsigned values; no physical conversion asserted. Axis labels are a fixed snapshot. Startup checksum must be corrected after external editing.`)}</description><CATEGORYMEM index="0" category="${categoryNames.indexOf(mapCategory(m))+1}"/>${axes}<XDFAXIS id="z"><EMBEDDEDDATA mmedaddress="${hex(address)}" mmedelementsizebits="${m.element_bytes*8}" mmedrowcount="${m.rows}" mmedcolcount="${m.columns}" mmedmajorstridebits="0" mmedminorstridebits="0"/><units>Raw ECU value</units><decimalpl>0</decimalpl><min>0</min><max>${2**(m.element_bytes*8)-1}</max><outputtype>2</outputtype><MATH equation="X"><VAR id="X"/></MATH></XDFAXIS></XDFTABLE>`;
  }).join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>\n<XDFFORMAT version="1.70"><XDFHEADER><flags>0x1</flags><deftitle>${xml(identity.label)} — ${xml(identity.id)} — raw maps</deftitle><description>${xml(`For ${bytes.length}-byte BIN files with CPU base ${hex(base)}. Addresses below are FILE OFFSETS (base already subtracted). Map definitions only; no feature patches or checksum plugin. Physical scaling is unresolved. Keep the source BIN unchanged and correct its startup checksum after TunerPro edits.`)}</description><BASEOFFSET offset="0" subtract="0"/><DEFAULTS datasizeinbits="8" sigdigits="0" outputtype="2" signed="0" lsbfirst="0" float="0"/><REGION type="0xFFFFFFFF" startaddress="0x0" size="${hex(bytes.length)}" regioncolor="0x0" regionflags="0x0" name="Binary File" desc="Exact loaded BIN size"/>${categoryNames.map((name,i)=>`<CATEGORY index="${hex(i)}" name="${xml(name)}"/>`).join('')}</XDFHEADER>\n${tables}\n</XDFFORMAT>\n`;
}

export function matchesMapVariant(bytes,reference,identity,maps){
  // Custom map-backed feature cells remain legitimate map edits. Normalizing
  // map bodies below still leaves every instruction/header guard to be checked.
  if(bytes.length!==reference.length||!maps.length||!speedState(bytes,identity).editable||featureStates(bytes,identity).some(f=>f.bytes&&!f.editable&&!f.mapBacked))return false;
  try{const base=baseAddress(bytes),normal=bytes.slice();for(const m of maps){const start=cellOffset(bytes,base,m,0),end=cellOffset(bytes,base,m,m.rows*m.columns-1)+m.element_bytes;normal.set(reference.subarray(start,end),start)}return matchesFeatureVariant(normal,reference,identity)}catch{return false}
}
