import {hex,sha256,inspect,baseAddress,differences,readCell,editCell,verifyStartupChecksum,correctStartupChecksum} from './tools-core.mjs';
import {SerialCapture} from './tools-serial.mjs';
const $=id=>document.getElementById(id),root=new URL('../',import.meta.url);
const error=e=>{$('tool-error').textContent=e.message||String(e);$('tool-error').hidden=false};
const guarded=fn=>async event=>{try{$('tool-error').hidden=true;await fn(event)}catch(e){error(e)}};
let original=null,draft=null,identity=null,maps=[],base=0,filename='',hash='',selected=null,cell=0,undo=[],generation=0,loading=false,origin='',repositoryImages=[];
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
function controls(){const checked=!!identity&&!!draft&&verifyStartupChecksum(draft,identity).status==='pass';$('repo-open').disabled=!repositoryImages.length||loading;for(const id of ['backup-save','backup-report','compare-file'])$(id).disabled=!original||loading;for(const id of ['draft-save','draft-report'])$(id).disabled=!checked||loading;for(const id of ['edit-reset','edit-undo'])$(id).disabled=!undo.length||loading;$('tune-map').disabled=!maps.length||loading;for(const id of ['cell-apply','cell-value'])$(id).disabled=!selected||loading}
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
async function report(){updateChecksum();const a=original.slice(),b=draft.slice(),changed=differences(a,b,base),snapshot={schema_version:1,source_name:filename,source_sha256:hash,registered_firmware:identity?.id||null,source:inspect(a),origin,draft:inspect(b),changed_bytes:changed,source_checksum:verifyStartupChecksum(a,identity),draft_checksum:verifyStartupChecksum(b,identity),checksum_repaired:changed.some(c=>c.address===0xF7FC||c.address===0xF7FD),checksum_method:'Analyst-selected trailer compensation at 0xF7FC; startup range only',flash_ready:false};return {...snapshot,draft_sha256:await sha256(b)}}
async function openBin(name,readBytes,source,expected=null){
  const token=++generation;loading=true;original=draft=identity=selected=null;maps=[];undo=[];$('bin-status').textContent='Opening '+name+'…';$('tune-grid').replaceChildren();$('bin-facts').replaceChildren();$('tune-map').replaceChildren(new Option('Open a registered BIN first',''));$('compare-file').value='';$('compare-status').textContent='';$('tune-status').textContent='';$('edit-status').textContent='';$('checksum-status').textContent='No BIN checked.';$('checksum-status').dataset.status='unverified';$('checksum-detail').textContent='';$('cell-info').textContent='Select a cell to edit.';controls();
  try{
    const bytes=new Uint8Array(await readBytes());
    if(![65536,59392].includes(bytes.length))throw Error('This tool accepts the two known BIN sizes: 65,536 or 59,392 bytes');
    const digest=await sha256(bytes),catalog=await catalogPromise;
    if(token!==generation)return;
    if(expected&&(digest!==expected.sha256||bytes.length!==expected.size))throw Error('Repository BIN does not match its catalogue identity. Nothing opened; reload the page and try again.');
    original=bytes;draft=bytes.slice();base=baseAddress(bytes);filename=name;hash=digest;origin=source;identity=expected||catalog.images.find(i=>i.sha256===hash)||null;
    updateChecksum();
    $('bin-status').textContent=identity?`${identity.label} · ${identity.variant} — exact registered hash`:'Unregistered BIN — inspection and comparison only; no layout is guessed';
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
$('backup-report').addEventListener('click',guarded(async()=>jsonSave(filename+'.identity.json',{source_name:filename,sha256:hash,registered_firmware:identity?.id||null,...inspect(original),checksum:verifyStartupChecksum(original,identity),origin})));
$('compare-file').addEventListener('change',guarded(async()=>{const file=$('compare-file').files[0];if(!file||!original)return;const token=generation;if(file.size!==original.length)throw Error('Comparison sizes differ; no padding or address shift is applied');const bytes=new Uint8Array(await file.arrayBuffer());if(token!==generation)return;const changes=differences(original,bytes,base);$('compare-status').textContent=changes.length?`${changes.length.toLocaleString()} changed bytes. First CPU address: ${hex(changes[0].address)}.`:'Byte-for-byte identical. This confirms file equality, not complete ECU coverage.'}));
function axis(map,name,index){const a=map[name]?.raw_values;if(map.kind==='2D_step_grid'&&a)return index===0?'≤'+a[0]:index===a.length?'>'+a.at(-1):a[index-1]+'…'+a[index];if(a)return a[index];if(name==='column_axis'&&map.kind==='1D_uniform_axis')return Number((map.input_min_raw+index*map.index_divisor/map.index_factor_raw).toFixed(3));return index+1}
function selectMap(){selected=maps.find(m=>m.id===$('tune-map').value)||null;cell=0;renderGrid();controls()}
function renderGrid(){
  if(!selected)return;const m=selected,count=m.rows*m.columns,values=Array.from({length:count},(_,i)=>readCell(draft,base,m,i)),lo=Math.min(...values),hi=Math.max(...values);
  const table=document.createElement('table');table.className=m.columns>15?'wide-map':'';const head=table.createTHead().insertRow();let th=document.createElement('th');th.textContent='Raw axes';head.append(th);for(let c=0;c<m.columns;c++){th=document.createElement('th');th.textContent=axis(m,'column_axis',c);head.append(th)}
  const tbody=table.createTBody(),stops=[[108,161,255],[91,221,232],[128,222,143],[255,223,109],[249,132,116]];
  for(let r=0;r<m.rows;r++){const row=tbody.insertRow();th=document.createElement('th');th.textContent=axis(m,'row_axis',r);row.append(th);for(let c=0;c<m.columns;c++){const i=r*m.columns+c,v=values[i],t=hi===lo?2:4*(v-lo)/(hi-lo),s=Math.min(3,Math.floor(t)),rgb=stops[s].map((a,k)=>Math.round(a+(stops[s+1][k]-a)*(t-s)));const button=document.createElement('button');button.type='button';button.className='tune-cell'+(readCell(original,base,m,i)!==v?' edited':'');button.textContent=v;button.dataset.index=i;button.style.setProperty('--cell-bg',`rgb(${rgb})`);button.setAttribute('aria-label',`Row ${r+1}, column ${c+1}, raw value ${v}`);button.setAttribute('aria-pressed',String(i===cell));button.title=button.getAttribute('aria-label');button.addEventListener('click',()=>{cell=i;showCell()});row.insertCell().append(button)}}
  $('tune-grid').replaceChildren(table);$('tune-status').textContent=`${identity.label} · ${identity.variant} · ${m.rows} × ${m.columns} · ${m.element_bytes*8}-bit · raw values. Colours span ${lo}–${hi}. Select a cell for its full value.`;showCell();
  const n=differences(original,draft,base).length;$('edit-status').textContent=`${n} changed bytes including checksum compensation. Startup checksum is verified again before saving. Physical units and flash readiness remain unverified.`;
}
function showCell(){if(!selected)return;const value=readCell(draft,base,selected,cell);$('cell-value').max=selected.element_bytes===2?65535:255;$('cell-value').value=value;$('cell-info').textContent=`Row ${Math.floor(cell/selected.columns)+1} · column ${cell%selected.columns+1} · CPU ${hex(Number(selected.data_address)+cell*selected.element_bytes)} · original ${readCell(original,base,selected,cell)} · draft ${value}`;document.querySelectorAll('.tune-cell').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.index)===cell)))}
$('tune-map').addEventListener('change',guarded(selectMap));
$('tune-form').addEventListener('submit',guarded(event=>{event.preventDefault();if(!selected||loading)return;if($('cell-value').value.trim()==='')throw Error('Enter a raw value');const change=editCell(draft,base,selected,cell,Number($('cell-value').value));if(change.before!==change.after)undo.push(change);updateChecksum();renderGrid();controls()}));
$('edit-undo').addEventListener('click',guarded(()=>{const change=undo.pop();if(!change)return;const m=maps.find(m=>m.id===change.map);editCell(draft,base,m,change.index,change.before);updateChecksum();renderGrid();controls()}));
$('edit-reset').addEventListener('click',guarded(()=>{draft=original.slice();undo=[];updateChecksum();renderGrid();controls()}));
$('draft-save').addEventListener('click',guarded(()=>{const verified=updateChecksum();controls();if(verified?.status!=='pass')throw Error('Save stopped: startup checksum is not verified');save(filename.replace(/\.bin$/i,'')+'.draft.bin',draft)}));
$('draft-report').addEventListener('click',guarded(async()=>jsonSave(filename+'.changes.json',await report())));
let terminalTail='';
const capture=new SerialCapture({onChunk:(item,count)=>{terminalTail=(terminalTail+`${item.elapsed_ms} ms  RX  ${item.bytes}\n`).slice(-12000);if($('terminal-toggle').checked)$('serial-log').textContent=terminalTail;$('serial-status').textContent=`Receiving: ${count.toLocaleString()} bytes · no transmitted data`;$('serial-save').disabled=false},onState:state=>{$('serial-status').textContent=state;$('serial-stop').disabled=!capture.port;$('serial-connect').disabled=!!capture.port}});
$('terminal-toggle').addEventListener('change',()=>{$('serial-terminal').hidden=!$('terminal-toggle').checked;if($('terminal-toggle').checked)$('serial-log').textContent=terminalTail});
if(!('serial' in navigator)){$('serial-connect').disabled=true;$('serial-status').textContent='Web Serial is unavailable in this browser. Use a supported desktop Chromium browser over HTTPS; local BIN tools still work.'}
$('serial-connect').addEventListener('click',guarded(async()=>{$('serial-connect').disabled=true;try{const port=await navigator.serial.requestPort();terminalTail='';$('serial-log').textContent='';await capture.connect(port,15625);$('serial-save').disabled=capture.count===0}finally{$('serial-connect').disabled=!!capture.port}}));
$('serial-stop').addEventListener('click',guarded(()=>capture.disconnect()));
$('serial-save').addEventListener('click',guarded(()=>jsonSave('xt660-rx-capture.json',capture.report())));
window.addEventListener('pagehide',()=>{capture.disconnect().catch(()=>{})});
