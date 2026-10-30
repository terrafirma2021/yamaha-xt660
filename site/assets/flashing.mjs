import {sha256, differences, hex} from './tools-core.mjs';
import {connectionForSelection, connectorSvg, kklSvg, checkFlashFile, signalNames, escapeHTML as esc} from './flashing-core.mjs';

const $ = id => document.getElementById(id);
const root = new URL('../', import.meta.url);
const context = $('vehicle-context');
let catalog, connections, selection, loaded, filename='', generation=0, busy=false;
const referenceCache=new Map(), mapsCache=new Map();
const fail=e=>{$('flash-error').textContent=e.message||String(e);$('flash-error').hidden=false;};
const guard=fn=>async e=>{try{$('flash-error').hidden=true;await fn(e);}catch(error){fail(error);}};
async function json(path) {const r=await fetch(new URL(path,root));if(!r.ok)throw Error('Could not load '+path);return r.json();}
const ready=Promise.all([json('firmware/catalog.json'),json('flashing/connections.json')]).then(values=>{[catalog,connections]=values;});
ready.catch(fail);

function renderSelection() {
  if(!catalog||!connections)return;
  const profile=selection?.profile||context.dataset.profile||$('ecu-select').value;
  const firmware=selection?.firmware||context.dataset.firmware||$('image-select').value;
  const image=catalog.images.find(i=>i.id===firmware);
  const match=connectionForSelection(connections,profile,image);
  $('connection-content').hidden=!match;
  if(!match){$('connection-title').textContent='No connector reference for this selection';$('connection-model').textContent='Select a matched motorcycle and firmware above.';return;}
  const {family,profile:p}=match;
  $('connection-title').textContent=image.label+' · '+family.positions+' positions';
  $('connection-model').textContent=p.model.toUpperCase()+' · '+p.year+' · '+image.variant;
  $('connection-badge').textContent=p.evidence;
  $('flash-connector-diagram').innerHTML=connectorSvg(family);
  $('flash-connector-diagram').dataset.family=family.id;
  $('flash-connector-diagram').dataset.firmware=image.id;
  $('connection-view').textContent=family.source.view;
  $('connection-terminals').innerHTML=family.slots.filter(s=>s.signal).map(s=>`<article class="signal-${s.signal}"><span>${signalNames[s.signal]}</span><strong>Upper ${s.column}</strong><small>${esc(s.wire)} · manual ${s.manual_position}</small></article>`).join('');
  $('kkl-diagram').innerHTML=kklSvg();
  $('connection-limit').textContent=family.source.note;
  $('connection-source-links').innerHTML=`<ul><li><a href="${new URL(family.source.url,root)}">${esc(family.source.title)} ↗</a></li><li><a href="${esc(family.manual_url)}">${esc(family.manual_title)} ↗</a></li><li><a href="${connections.kkl.source_url}">${esc(connections.kkl.source_title)} ↗</a></li></ul>`;
  if(!loaded&&!busy)$('flash-repo-bin').value=image.id;
}
document.addEventListener('vehiclechange',event=>{selection=event.detail;ready.then(renderSelection).catch(fail);});
ready.then(()=>{
  $('flash-repo-bin').replaceChildren(...catalog.images.map(i=>new Option(i.label+' · '+i.variant,i.id)));
  $('flash-repo-bin').disabled=false;$('flash-repo-open').disabled=false;renderSelection();
}).catch(fail);

async function reference(i) {
  if(!referenceCache.has(i.id))referenceCache.set(i.id,(async()=>{
    const r=await fetch(new URL('tools/bins/'+i.id+'.bin',root));
    if(!r.ok)throw Error('Reference BIN could not be loaded');
    const b=new Uint8Array(await r.arrayBuffer());
    if(b.length!==i.size||await sha256(b)!==i.sha256)throw Error('Reference BIN hash mismatch');
    return b;
  })().catch(e=>{referenceCache.delete(i.id);throw e;}));
  return referenceCache.get(i.id);
}
function maps(i) {if(!mapsCache.has(i.id))mapsCache.set(i.id,json('tools/maps/'+i.id+'.json').catch(e=>{mapsCache.delete(i.id);throw e;}));return mapsCache.get(i.id);}
function controls() {
  $('flash-repo-open').disabled=busy||!catalog;$('flash-repo-bin').disabled=busy||!catalog;
  for(const id of ['flash-save-copy','flash-save-report','flash-compare-file'])$(id).disabled=busy||!loaded;
}
function renderChecks(result) {
  const check=(label,state,value)=>`<article data-check="${state}"><span>${label}</span><strong>${esc(value)}</strong></article>`;
  $('flash-checks').innerHTML=check('BIN identity',result.identity?'known':'unknown',result.identity_match)+
    check('Selected reference',result.selected_layout_matches?'known':'unknown',result.selected_layout_matches?'Layout matches':'Does not match')+
    check('Startup checksum',result.checksum.status,result.checksum.status.toUpperCase()+' · '+result.checksum.actual)+
    check('Boot coverage',result.boot_reference_matches?'known':'unknown',result.boot_reference_matches?'Matches registered boot':result.boot.startsWith('FF')?'Missing · FF placeholder':'Populated · unidentified');
  const facts={'File':filename,'Reference':result.identity?result.identity.label+' · '+result.identity.variant:'No registered layout',
    'SHA-256':result.sha256,'CPU range':hex(result.base_address)+'–'+hex(result.end_address),
    'Compatibility':'Layout matching does not identify the attached ECU. Live flashing remains unavailable.'};
  $('flash-bin-facts').replaceChildren(...Object.entries(facts).flatMap(([k,v])=>{const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=k;dd.textContent=v;return [dt,dd];}));
}
async function openFile(name, read, expected) {
  const token=++generation;busy=true;loaded=null;filename=name;
  $('flash-bin-status').textContent='Checking '+name+'…';$('flash-checks').replaceChildren();$('flash-bin-facts').replaceChildren();$('flash-compare-file').value='';$('flash-compare-status').textContent='';controls();
  try {
    await ready;
    const bytes=new Uint8Array(await read());
    if(expected&&(bytes.length!==expected.size||await sha256(bytes)!==expected.sha256))throw Error('Repository BIN does not match its catalogue hash');
    const selectedId=selection?.firmware||context.dataset.firmware||$('image-select').value;
    const result=await checkFlashFile(bytes,catalog,selectedId,reference,maps);
    if(token!==generation)return;
    loaded={bytes,result};renderChecks(result);
    $('flash-bin-status').textContent='Checked '+name+'. Original bytes preserved.';
  } catch(e) {if(token===generation)$('flash-bin-status').textContent='BIN could not be checked.';throw e;}
  finally {if(token===generation){busy=false;controls();}}
}
$('flash-bin-file').addEventListener('change',guard(async()=>{
  const f=$('flash-bin-file').files[0];if(!f)return;
  await openFile(f.name,()=>{if(![65536,59392].includes(f.size))throw Error('Expected a 65,536-byte or 59,392-byte BIN');return f.arrayBuffer();});
}));
$('flash-repo-open').addEventListener('click',guard(async()=>{
  const i=catalog.images.find(i=>i.id===$('flash-repo-bin').value);if(!i)return;
  $('flash-bin-file').value='';await openFile(i.file.split('/').at(-1),()=>reference(i),i);
}));
function save(name,data,type='application/octet-stream') {const url=URL.createObjectURL(new Blob([data],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('flash-save-copy').addEventListener('click',guard(()=>save(filename,loaded.bytes)));
$('flash-save-report').addEventListener('click',guard(()=>save(filename+'.checks.json',JSON.stringify({source_name:filename,...loaded.result},null,2)+'\n','application/json')));
$('flash-compare-file').addEventListener('change',guard(async()=>{
  const f=$('flash-compare-file').files[0], current=loaded;if(!f||!current)return;
  if(f.size!==current.bytes.length)throw Error('Comparison sizes differ; no padding or address shift is applied');
  const bytes=new Uint8Array(await f.arrayBuffer());if(current!==loaded)return;
  const changes=differences(current.bytes,bytes,current.result.base_address);
  $('flash-compare-status').textContent=changes.length?`${changes.length.toLocaleString()} changed bytes; first CPU address ${hex(changes[0].address)}.`:'Byte-for-byte identical. File equality does not establish complete ECU backup coverage.';
}));
