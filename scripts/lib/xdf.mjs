import {featurePatches} from './xdf-features.mjs';
import {readCell,cellOffset,hex} from '../../flasher/core/tools-core.mjs';
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
const xml=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
export function exportXdf(bytes,base,maps,identity,{features=true}={}){
  if(!identity||!maps.length)throw Error('Load a recognised BIN before exporting XDF');
  const patches=features?featurePatches(bytes,identity):[];
  const categoryNames=[...new Set([...maps.map(m=>mapCategory(m)),...patches.map(p=>p.category)])];
  const packed=a=>a.map(v=>v.toString(16).padStart(2,'0')).join('').toUpperCase();
  const patchXml=patches.map((p,j)=>`<XDFPATCH uniqueid="${hex(0x1000+j)}"><title>${xml(p.title)}</title><description>${xml(p.description)}</description><CATEGORYMEM index="0" category="${categoryNames.indexOf(p.category)+1}"/>${p.entries.map((e,i)=>`<XDFPATCHENTRY name="Part ${i+1}" address="${hex(e.address)}" datasize="${hex(e.before.length)}" patchdata="${packed(e.after)}" basedata="${packed(e.before)}"/>`).join('')}</XDFPATCH>`).join('\n');
  const tables=maps.map((m,j)=>{
    const address=cellOffset(bytes,base,m,0);readCell(bytes,base,m,m.rows*m.columns-1);
    const axes=[['x','column_axis',m.columns],['y','row_axis',m.rows]].map(([id,key,n])=>`<XDFAXIS id="${id}" uniqueid="0x0"><EMBEDDEDDATA mmedelementsizebits="16" mmedcolcount="${n}"/><units>Raw axis</units><indexcount>${n}</indexcount><decimalpl>4</decimalpl><outputtype>4</outputtype><datatype>0</datatype><unittype>0</unittype><DALINK index="0"/>${Array.from({length:n},(_,i)=>`<LABEL index="${i}" value="${xml(axisLabel(m,key,i))}"/>`).join('')}<MATH equation="X"><VAR id="X"/></MATH></XDFAXIS>`).join('');
    return `<XDFTABLE uniqueid="${hex(j+1)}" flags="0x30"><title>${xml(m.display_name||m.id)}</title><description>${xml(`${m.id}; CPU ${m.data_address}; ${m.confidence||'Recovered layout'}. Raw unsigned values; no physical conversion asserted. Axis labels are a fixed snapshot. Startup checksum must be corrected after external editing.`)}</description><CATEGORYMEM index="0" category="${categoryNames.indexOf(mapCategory(m))+1}"/>${axes}<XDFAXIS id="z"><EMBEDDEDDATA mmedaddress="${hex(address)}" mmedelementsizebits="${m.element_bytes*8}" mmedrowcount="${m.rows}" mmedcolcount="${m.columns}" mmedmajorstridebits="0" mmedminorstridebits="0"/><units>Raw ECU value</units><decimalpl>0</decimalpl><min>0</min><max>${2**(m.element_bytes*8)-1}</max><outputtype>2</outputtype><MATH equation="X"><VAR id="X"/></MATH></XDFAXIS></XDFTABLE>`;
  }).join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>\n<XDFFORMAT version="1.70"><XDFHEADER><flags>0x1</flags><deftitle>${xml(identity.label)} — ${xml(identity.id)} — raw maps</deftitle><description>${xml(`For ${bytes.length}-byte BIN files with CPU base ${hex(base)}. Addresses below are FILE OFFSETS (base already subtracted). ${features?'Raw map tables and reversible feature patches. No checksum plugin.':'Map definitions only; no feature patches or checksum plugin.'} Physical scaling is unresolved. Keep the source BIN unchanged and correct its startup checksum after TunerPro edits.`)}</description><BASEOFFSET offset="0" subtract="0"/><DEFAULTS datasizeinbits="8" sigdigits="0" outputtype="2" signed="0" lsbfirst="0" float="0"/><REGION type="0xFFFFFFFF" startaddress="0x0" size="${hex(bytes.length)}" regioncolor="0x0" regionflags="0x0" name="Binary File" desc="Exact loaded BIN size"/>${categoryNames.map((name,i)=>`<CATEGORY index="${hex(i)}" name="${xml(name)}"/>`).join('')}</XDFHEADER>\n${tables}${features?'\n'+patchXml:''}\n</XDFFORMAT>\n`;
}
