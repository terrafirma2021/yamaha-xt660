import {hex,sha256,inspect,baseAddress,differences,readCell,editCell,verifyStartupChecksum,correctStartupChecksum} from './tools-core.mjs';
import {featureStates,setFeature,matchesFeatureVariant} from './tools-features.mjs';
import {speedState,setSpeed} from './tools-speed.mjs';
import {createWorkspace} from './tools-workspace.mjs';
import {matchesMapVariant} from './tools-map-core.mjs';
const $=id=>document.getElementById(id),root=new URL('../',import.meta.url);
const error=e=>{$('tool-error').textContent=e.message||String(e);$('tool-error').hidden=false};
const guarded=fn=>async event=>{try{$('tool-error').hidden=true;await fn(event)}catch(e){error(e)}};
let original=null,draft=null,identity=null,maps=[],base=0,filename='',hash='',selected=null,cell=0,undo=[],redo=[],generation=0,loading=false,origin='',repositoryImages=[];
let matchMethod='none';
const referenceCache=new Map();
async function referenceBin(image){
  if(!referenceCache.has(image.id))referenceCache.set(image.id,(async()=>{
    const response=await fetch(new URL('tools/bins/'+image.id+'.bin',root));
    if(!response.ok)throw Error('Reference BIN could not be loaded');
    const bytes=new Uint8Array(await response.arrayBuffer());
    if(await sha256(bytes)!==image.sha256)throw Error('Reference BIN hash mismatch');
    return bytes;
  })().catch(e=>{referenceCache.delete(image.id);throw e}));
  return referenceCache.get(image.id);
}
function renderFeatures(){
  const focused=document.activeElement?.id;
  const list=$('feature-list');list.replaceChildren();
  for(const f of featureStates(draft,identity)){
    const row=document.createElement('div');row.className='feature-row';row.dataset.available=String(f.editable&&!loading);
    const heading=document.createElement('div');heading.className='feature-heading';
    const name=document.createElement('strong');name.id='feature-'+f.id+'-name';name.textContent=f.name;
    const group=document.createElement('div');group.className='feature-options';group.setAttribute('role','radiogroup');group.setAttribute('aria-labelledby',name.id);
    for(const enabled of [true,false]){
      const label=document.createElement('label'),input=document.createElement('input');
      input.type='radio';input.name='feature-'+f.id;input.id='feature-'+f.id+(enabled?'-enabled':'-disabled');input.value=String(enabled);
      input.checked=f.state===(enabled?'enabled':'disabled');input.disabled=loading||!f.editable;
      input.addEventListener(f.legacyPatch?'click':'change',guarded(()=>{
        if(loading||!input.checked)return;
        const change=setFeature(draft,identity,f.id,enabled);
        if(change.changes.length)record(change);
        updateChecksum();renderGrid();controls();
        $('feature-status').textContent=f.name+(enabled?' enabled':' disabled')+' in the draft. Startup checksum corrected.';
      }));
      label.append(input,document.createTextNode(enabled?'Enabled':'Disabled'));group.append(label);
    }
    heading.append(name,group);row.append(heading);
    if(f.detail){const detail=document.createElement('p');detail.textContent=f.detail;row.append(detail)}
    list.append(row);
  }
  if(focused?.startsWith('feature-'))$(focused)?.focus({preventScroll:true});
}
const catalogPromise=fetch(new URL('firmware/catalog.json',root)).then(r=>{if(!r.ok)throw Error('Firmware catalogue could not be loaded');return r.json()});
// Capture a rejection immediately; the file handler displays it when needed.
catalogPromise.then(catalog=>{
  repositoryImages=catalog.images;
  $('repo-bin').replaceChildren(...repositoryImages.map(i=>new Option(i.label+' · '+i.variant,i.id)));
  const requested=new URL(location.href).searchParams.get('firmware');
  if(repositoryImages.some(i=>i.id===requested))$('repo-bin').value=requested;
  $('repo-bin').disabled=false;controls();
}).catch(error);
function save(name,data,type='application/octet-stream'){const url=URL.createObjectURL(new Blob([data],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function jsonSave(name,value){save(name,JSON.stringify(value,null,2)+'\n','application/json')}
function facts(values){const dl=$('bin-facts');dl.replaceChildren();for(const [key,value] of Object.entries(values)){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=key;dd.textContent=String(value);dl.append(dt,dd)}}
function controls(){const checked=!!identity&&!!draft&&verifyStartupChecksum(draft,identity).status==='pass';$('repo-open').disabled=!repositoryImages.length||loading;for(const id of ['backup-save','backup-report','compare-file'])$(id).disabled=!original||loading;for(const id of ['draft-save','draft-report'])$(id).disabled=!checked||loading;for(const id of ['edit-reset','edit-undo'])$(id).disabled=!undo.length||loading;$('tune-map').disabled=!maps.length||loading;$('edit-redo').disabled=!redo.length||loading;renderFeatures();renderSpeed();workspace.render()}
function renderSpeed(){
  const s=speedState(draft,identity),ready=s.editable&&!loading;
  $('speed-output-row').dataset.available=String(ready);
  $('speed-form').dataset.available=String(ready&&s.enabled);
  for(const id of ['speed-enabled','speed-disabled','speed-apply'])$(id).disabled=!ready;
  $('speed-offset').disabled=!ready||!s.enabled;
  $('speed-apply').disabled=!ready||!s.enabled;
  $('speed-enabled').checked=s.enabled===true;$('speed-disabled').checked=s.enabled===false;
  $('speed-offset').value=s.offset??0;
  $('speed-status').textContent=!ready?'No supported BIN loaded, or speed patch bytes are unverified.':s.enabled?`Enabled · ${s.offset>0?'+':''}${s.offset} pulses per reply. Zero remains zero; bounds 0–255. Hardware untested.`:'Disabled · speed field sends zero. Other reply fields continue normally. Hardware untested.';
}
function applySpeed(enabled,offset){
  if(loading)return;
  const change=setSpeed(draft,identity,enabled,offset);
  if(change.changes.length)record(change);
  updateChecksum();controls();
}
$('speed-form').addEventListener('submit',guarded(event=>{event.preventDefault();if($('speed-offset').value.trim()==='')throw Error('Enter a whole pulse offset');applySpeed(true,Number($('speed-offset').value))}));
for(const enabled of [true,false])$('speed-'+(enabled?'enabled':'disabled')).addEventListener('change',guarded(()=>applySpeed(enabled,speedState(draft,identity).offset)));
function updateChecksum(){
  if(!original||!draft)return;
  const source=verifyStartupChecksum(original,identity);let result=verifyStartupChecksum(draft,identity);
  if(identity&&result.status!=='unverified')result=correctStartupChecksum(draft,identity);
  $('checksum-status').dataset.status=result.status;
  $('checksum-status').textContent=`Original: ${source.status.toUpperCase()} (${source.actual}). Editable copy: ${result.status.toUpperCase()} (${result.actual}). ${result.expected?'Expected '+result.expected+' over '+result.range+'. Automatic correction is on.':'No matching checksum profile; no correction applied.'}`;
  const offset=0xF7FC-base,changed=original[offset]!==draft[offset]||original[offset+1]!==draft[offset+1];
  $('checksum-detail').textContent=changed?'The editable copy includes compensation at CPU 0xF7FC–0xF7FD. The original is untouched. This is reviewed trailer padding, not an identified factory checksum field.':'Only the application startup checksum is covered. Passing does not verify the boot region, other storage or ECU compatibility.';
  return result;
}
async function report(){updateChecksum();const a=original.slice(),b=draft.slice(),changed=differences(a,b,base),snapshot={schema_version:1,source_name:filename,source_sha256:hash,registered_firmware:identity?.id||null,identity_match:matchMethod,speed_output:{...speedState(b,identity),unit:"pulses per reply",hardware_verified:false},features:featureStates(b,identity).map(f=>({id:f.id,state:f.state,legacy_threshold_patch:f.legacyPatch,hardware_verified:false})),source:inspect(a),origin,draft:inspect(b),changed_bytes:changed,source_checksum:verifyStartupChecksum(a,identity),draft_checksum:verifyStartupChecksum(b,identity),checksum_repaired:changed.some(c=>c.address===0xF7FC||c.address===0xF7FD),checksum_method:'Analyst-selected trailer compensation at 0xF7FC; startup range only',flash_ready:false};return {...snapshot,draft_sha256:await sha256(b)}}
async function openBin(name,readBytes,source,expected=null){
  const token=++generation;loading=true;matchMethod='none';$('feature-status').textContent='Opening BIN…';original=draft=identity=selected=null;maps=[];undo=[];redo=[];$('bin-status').textContent='Opening '+name+'…';$('tune-grid').replaceChildren();$('bin-facts').replaceChildren();$('tune-map').replaceChildren(new Option('Open a registered BIN first',''));$('compare-file').value='';$('compare-status').textContent='';$('tune-status').textContent='';$('edit-status').textContent='';$('checksum-status').textContent='No BIN checked.';$('checksum-status').dataset.status='unverified';$('checksum-detail').textContent='';$('cell-info').textContent='Select a cell to edit.';controls();
  try{
    const bytes=new Uint8Array(await readBytes());
    if(![65536,59392].includes(bytes.length))throw Error('This tool accepts the two known BIN sizes: 65,536 or 59,392 bytes');
    const digest=await sha256(bytes),catalog=await catalogPromise;
    if(token!==generation)return;
    if(expected&&(digest!==expected.sha256||bytes.length!==expected.size))throw Error('Repository BIN does not match its catalogue identity. Nothing opened; reload the page and try again.');
    original=bytes;draft=bytes.slice();base=baseAddress(bytes);filename=name;hash=digest;origin=source;identity=expected||catalog.images.find(i=>i.sha256===hash)||null;
    matchMethod=identity?'exact registered hash':'none';
    if(!identity){
      for(const candidate of catalog.images.filter(i=>i.size===bytes.length)){
        const reference=await referenceBin(candidate);if(token!==generation)return;
        const layoutsResponse=await fetch(new URL('tools/maps/'+candidate.id+'.json',root));
        if(!layoutsResponse.ok)continue;const candidateMaps=await layoutsResponse.json();if(token!==generation)return;
        if(matchesFeatureVariant(bytes,reference,candidate)||matchesMapVariant(bytes,reference,candidate,candidateMaps)){identity=candidate;matchMethod='recognised map/feature-edited layout; source variant is not established';break}
      }
    }
    updateChecksum();
    $('feature-status').textContent=identity?'States detected from BIN bytes. Changes affect the draft only.':'Unregistered BIN: feature controls are unavailable.';
    $('bin-status').textContent=identity?`${identity.label} — ${matchMethod}`:'Unregistered BIN — inspection and comparison only; no layout is guessed';
    const info=inspect(original);facts({'File':filename,'Source':origin,'SHA-256':hash,'CPU range':hex(base)+'–'+hex(info.end_address),'Application word sum':info.application_word_sum,'Boot':info.boot,'Coverage':'Full ECU backup status is unverified; boot and persistent storage need separate coverage.'});
    if(identity){
      const r=await fetch(new URL('tools/maps/'+identity.id+'.json',root));if(!r.ok)throw Error('Map layouts could not be loaded');const loaded=await r.json();if(token!==generation)return;
      for(const m of loaded)readCell(draft,base,m,m.rows*m.columns-1);maps=loaded;
      $('tune-map').replaceChildren(...maps.map(m=>new Option(m.display_name+' · '+m.data_address,m.id)));selectMap();
    }
  }catch(e){if(token===generation){$('bin-status').textContent=original?'BIN opened; map editing unavailable.':'BIN could not be opened';throw e}}
  finally{if(token===generation){loading=false;controls()}}
}
$('bin-file').addEventListener('change',guarded(async()=>{
  const file=$('bin-file').files[0];if(!file)return;
  await openBin(file.name,async()=>{if(![65536,59392].includes(file.size))throw Error('This tool accepts the two known BIN sizes: 65,536 or 59,392 bytes');return file.arrayBuffer()},'Local file; this tool did not dump the ECU');
}));
$('repo-open').addEventListener('click',guarded(async()=>{
  const image=repositoryImages.find(i=>i.id===$('repo-bin').value);if(!image)return;
  $('bin-file').value='';
  await openBin(image.file.split('/').at(-1),async()=>{
    const response=await fetch(new URL('tools/bins/'+image.id+'.bin',root));
    if(!response.ok)throw Error('Repository BIN could not be downloaded. Try again or open a local file.');
    return response.arrayBuffer();
  },'Repository BIN; this tool did not dump the ECU',image);
}));
$('backup-save').addEventListener('click',guarded(()=>save(filename.replace(/\.bin$/i,'')+'-untouched.bin',original)));
$('backup-report').addEventListener('click',guarded(async()=>jsonSave(filename+'.identity.json',{source_name:filename,sha256:hash,registered_firmware:identity?.id||null,identity_match:matchMethod,speed_output:{...speedState(original,identity),unit:"pulses per reply",hardware_verified:false},features:featureStates(original,identity).map(f=>({id:f.id,state:f.state,legacy_threshold_patch:f.legacyPatch})),...inspect(original),checksum:verifyStartupChecksum(original,identity),origin})));
$('compare-file').addEventListener('change',guarded(async()=>{const file=$('compare-file').files[0];if(!file||!original)return;const token=generation;if(file.size!==original.length)throw Error('Comparison sizes differ; no padding or address shift is applied');const bytes=new Uint8Array(await file.arrayBuffer());if(token!==generation)return;const changes=differences(original,bytes,base);$('compare-status').textContent=changes.length?`${changes.length.toLocaleString()} changed bytes. First CPU address: ${hex(changes[0].address)}.`:'Byte-for-byte identical. This confirms file equality, not complete ECU coverage.'}));
function record(change){undo.push(change);redo=[]}
const workspace=createWorkspace({
  getState:()=>({original,draft,identity,maps,base,selected,loading}),
  onSelect:id=>{$('tune-map').value=id;selectMap()},
  onExport:save,
  onCommit:changes=>{
    if(!selected||loading)return;
    // Validate every proposed cell before touching the draft, then record bytes.
    const copy=draft.slice(),bytes=[];
    for(const c of changes){if(readCell(draft,base,selected,c.index)!==c.before)throw Error('Preview is stale; preview the edit again');editCell(copy,base,selected,c.index,c.after)}
    for(const c of changes){const address=Number(selected.data_address)+c.index*selected.element_bytes;for(let j=0;j<selected.element_bytes;j++){const a=address+j;if(draft[a-base]!==copy[a-base])bytes.push({address:a,before:draft[a-base],after:copy[a-base]})}}
    if(bytes.length){draft=copy;record({kind:'map-batch',map:selected.id,changes:bytes})}updateChecksum();controls();renderGrid();
  }
});
function selectMap(){selected=maps.find(m=>m.id===$('tune-map').value)||null;controls();renderGrid()}
function renderGrid(){workspace.render();if(!draft)return;const n=differences(original,draft,base).length;$('edit-status').textContent=`${n} changed bytes including checksum compensation. Startup checksum is verified again before saving.`}
$('tune-map').addEventListener('change',guarded(selectMap));
function replay(change,forward){
  if(change.changes){for(const c of change.changes)draft[c.address-base]=forward?c.after:c.before}
  else{const m=maps.find(m=>m.id===change.map);editCell(draft,base,m,change.index,forward?change.after:change.before)}
  updateChecksum();controls();renderGrid();
}
$('edit-undo').addEventListener('click',guarded(()=>{const c=undo.pop();if(c){redo.push(c);replay(c,false)}}));
$('edit-redo').addEventListener('click',guarded(()=>{const c=redo.pop();if(c){undo.push(c);replay(c,true)}}));
$('edit-reset').addEventListener('click',guarded(()=>{draft=original.slice();undo=[];redo=[];$('feature-status').textContent='Edits discarded; original feature states restored.';updateChecksum();controls();renderGrid()}));
$('draft-save').addEventListener('click',guarded(()=>{const verified=updateChecksum();controls();if(verified?.status!=='pass')throw Error('Save stopped: startup checksum is not verified');save(filename.replace(/\.bin$/i,'')+'.draft.bin',draft)}));
$('draft-report').addEventListener('click',guarded(async()=>jsonSave(filename+'.changes.json',await report())));
