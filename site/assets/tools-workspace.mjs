import {readCell,hex} from './tools-core.mjs';
import {axisLabel,mapCategory,rectangle,indices,previewEdit,exportXdf} from './tools-map-core.mjs';
export function createWorkspace({getState,onSelect,onCommit,onExport}){
  const $=id=>document.getElementById(id);
  let anchor=0,focus=0,pending=[],lastMap=null,lastOriginal=null,lastMaps=null,drag=false;
  const message=text=>$('map-message').textContent=text;
  const safe=fn=>event=>{try{fn(event)}catch(e){message(e.message)}};
  const state=()=>{const s=getState();return {...s,m:s.selected}};
  const values=(bytes,s)=>Array.from({length:s.m.rows*s.m.columns},(_,i)=>readCell(bytes,s.base,s.m,i));
  const rect=()=>rectangle(state().m,anchor,focus);
  function editable(){const s=state();return !!s.m&&!s.loading&&$('map-display').value==='draft'}
  function select(a,b){const hadPreview=pending.length;anchor=a;focus=b;pending=[];if(hadPreview)grid();else{selection();graph();previewPanel()}}
  function previewPanel(){
    $('map-preview-panel').hidden=!pending.length;$('map-apply').disabled=!pending.length||!editable();
    if(pending.length){const delta=pending.map(p=>p.after-p.before);$('map-preview-summary').textContent=`${pending.length} cells will change · delta ${Math.min(...delta)} to ${Math.max(...delta)}`}
  }
  function selection(){
    const s=state();if(!s.m)return;const selected=new Set(indices(s.m,rect())),r=rect();
    for(const b of $('tune-grid').querySelectorAll('button[data-index]')){const i=Number(b.dataset.index);b.setAttribute('aria-pressed',String(selected.has(i)));b.tabIndex=i===focus?0:-1}
    const before=readCell(s.original,s.base,s.m,focus),after=readCell(s.draft,s.base,s.m,focus);
    $('cell-info').textContent=`${selected.size} selected · rows ${r.r0+1}–${r.r1+1}, columns ${r.c0+1}–${r.c1+1} · ${hex(Number(s.m.data_address)+focus*s.m.element_bytes)} · original ${before} → edited ${after} (${after-before>=0?'+':''}${after-before})`;
  }
  function colour(v,lo,hi){const stops=[[108,161,255],[91,221,232],[128,222,143],[255,223,109],[249,132,116]],t=hi===lo?2:4*(v-lo)/(hi-lo),j=Math.min(3,Math.max(0,Math.floor(t)));return `rgb(${stops[j].map((a,k)=>Math.round(a+(stops[j+1][k]-a)*(t-j))).join(',')})`}
  function grid(){
    const s=state();if(!s.m){$('tune-grid').replaceChildren();$('cell-info').textContent='No selection.';$('map-angle-label').hidden=true;graph();previewPanel();return}
    const m=s.m,old=values(s.original,s),draft=values(s.draft,s),proposed=new Map(pending.map(p=>[p.index,p.after])),shown=draft.map((v,i)=>proposed.get(i)??v),mode=$('map-display').value;
    const data=shown.map((v,i)=>mode==='original'?old[i]:mode==='difference'?v-old[i]:v),lo=Math.min(...data),hi=Math.max(...data);
    const table=document.createElement('table');table.className='workspace-grid';table.style.setProperty('--map-columns',m.columns);table.style.fontSize=m.columns>25?'9px':m.columns>15?'10px':'12px';
    if($('map-fit').value==='readable')table.style.minWidth=(m.columns*58+70)+'px';
    const header=table.createTHead().insertRow(),corner=document.createElement('th');corner.textContent='Raw axes';header.append(corner);
    for(let c=0;c<m.columns;c++){const th=document.createElement('th');th.textContent=axisLabel(m,'column_axis',c);header.append(th)}
    const body=table.createTBody();
    for(let r=0;r<m.rows;r++){const row=body.insertRow(),th=document.createElement('th');th.textContent=axisLabel(m,'row_axis',r);row.append(th);
      for(let c=0;c<m.columns;c++){
        const i=r*m.columns+c,b=document.createElement('button');b.type='button';b.className='tune-cell'+(old[i]!==draft[i]?' edited':'')+(proposed.has(i)?' proposed':'');b.dataset.index=i;b.textContent=mode==='difference'&&data[i]>0?'+'+data[i]:data[i];b.style.setProperty('--cell-bg',colour(data[i],lo,hi));
        b.title=`Row ${r+1}, column ${c+1}; original ${old[i]}, edited ${draft[i]}`+(proposed.has(i)?`, proposed ${shown[i]}`:'');b.setAttribute('aria-label',b.title);
        b.addEventListener('pointerdown',e=>{if(e.button!==0)return;drag=true;select(e.shiftKey?anchor:i,i);b.focus({preventScroll:true})});
        b.addEventListener('pointerenter',()=>{if(drag){focus=i;selection();graph()}});
        b.addEventListener('click',e=>{if(e.detail===0)select(e.shiftKey?anchor:i,i)});
        row.insertCell().append(b);
      }
    }
    $('tune-grid').replaceChildren(table);selection();graph();previewPanel();
  }
  function library(){
    const s=state(),query=$('map-search').value.trim().toLowerCase(),category=$('map-category').value,changed=$('map-changed').checked;
    const visible=s.maps.filter(m=>(!category||mapCategory(m)===category)&&(!query||`${m.display_name} ${m.id} ${m.data_address}`.toLowerCase().includes(query))).map(m=>({m,n:Array.from({length:m.rows*m.columns},(_,i)=>readCell(s.original,s.base,m,i)!==readCell(s.draft,s.base,m,i)).filter(Boolean).length})).filter(x=>!changed||x.n);
    $('map-count').textContent=`${visible.length} / ${s.maps.length} maps`;$('map-list').replaceChildren();
    for(const {m,n} of visible){const b=document.createElement('button');b.type='button';b.className='map-item';b.setAttribute('aria-pressed',String(m.id===s.m?.id));const name=document.createElement('strong'),meta=document.createElement('span');name.textContent=m.display_name||m.id;meta.textContent=`${mapCategory(m)} · ${m.rows} × ${m.columns}`+(n?` · ${n} edited`:'');b.append(name,meta);b.addEventListener('click',()=>onSelect(m.id));$('map-list').append(b)}
  }
  function graph(){
    const canvas=$('map-graph'),ctx=canvas.getContext('2d'),s=state(),W=canvas.width,H=canvas.height;ctx.clearRect(0,0,W,H);if(!s.m)return;
    const m=s.m,a=values(s.draft,s),o=values(s.original,s);for(const p of pending)a[p.index]=p.after;
    const ink=getComputedStyle(document.documentElement).getPropertyValue('--ink').trim()||'#ccc';ctx.font='14px sans-serif';ctx.fillStyle=ink;
    const surface=$('map-graph-mode').value==='surface'&&m.rows>1&&m.columns>1;
    $('map-angle-label').hidden=!surface;
    $('map-graph-key').textContent=(surface?'Colours: low values in blue to high values in red.':'Blue: edited or preview · grey: original.')+' Graph coordinates use cell positions; raw axis values are shown in the grid.';
    if(surface){
      const lo=Math.min(...a),hi=Math.max(...a),angle=Number($('map-angle').value)*Math.PI/180;
      const project=(r,c)=>{const x=c/(m.columns-1)-.5,y=r/(m.rows-1)-.5,z=(a[r*m.columns+c]-lo)/(hi-lo||1);return [W/2+(x*Math.cos(angle)-y*Math.sin(angle))*480,H*.68+(x*Math.sin(angle)+y*Math.cos(angle))*90-z*150]};
      const polys=[];for(let r=0;r<m.rows-1;r++)for(let c=0;c<m.columns-1;c++)polys.push({r,c,depth:(c/(m.columns-1)-.5)*Math.sin(angle)+(r/(m.rows-1)-.5)*Math.cos(angle)});
      polys.sort((a,b)=>a.depth-b.depth);
      for(const {r,c} of polys){const pts=[project(r,c),project(r,c+1),project(r+1,c+1),project(r+1,c)];ctx.beginPath();pts.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();ctx.fillStyle=colour(a[r*m.columns+c],lo,hi);ctx.fill();ctx.strokeStyle='#07111b55';ctx.stroke()}
      ctx.fillStyle=ink;ctx.fillText(`Edited surface · raw ${lo}–${hi} · ${m.rows} rows × ${m.columns} columns`,20,22);
    }else{
      const row=Math.floor(focus/m.columns),v=a.slice(row*m.columns,(row+1)*m.columns),old=o.slice(row*m.columns,(row+1)*m.columns),lo=Math.min(...v,...old),hi=Math.max(...v,...old),x=i=>55+i*(W-85)/Math.max(1,v.length-1),y=z=>H-35-(z-lo)*(H-85)/(hi-lo||1);
      ctx.strokeStyle=ink;ctx.globalAlpha=.15;for(let t=0;t<5;t++){ctx.beginPath();ctx.moveTo(55,50+t*(H-85)/4);ctx.lineTo(W-30,50+t*(H-85)/4);ctx.stroke()}ctx.globalAlpha=1;
      for(const [line,col] of [[old,'#8993a3'],[v,'#668cff']]){ctx.strokeStyle=col;ctx.lineWidth=2;ctx.beginPath();line.forEach((z,i)=>i?ctx.lineTo(x(i),y(z)):ctx.moveTo(x(i),y(z)));ctx.stroke();for(let i=0;i<line.length;i++){ctx.beginPath();ctx.arc(x(i),y(line[i]),2.5,0,Math.PI*2);ctx.fillStyle=col;ctx.fill()}}
      ctx.fillStyle=ink;ctx.fillText(`Row ${row+1} · axis ${axisLabel(m,'row_axis',row)} · raw ${lo}–${hi}`,20,22);ctx.fillText(String(axisLabel(m,'column_axis',0)),55,H-10);ctx.fillText(String(axisLabel(m,'column_axis',m.columns-1)),W-85,H-10);
    }
  }
  function preview(){const s=state();if(!editable())return;const op=$('map-operation').value,raw=$('map-factor').value;if(['set','add','multiply'].includes(op)&&!raw.trim())throw Error('Enter a value');pending=previewEdit(s.m,values(s.draft,s),values(s.original,s),rect(),op,Number(raw),$('map-paste').value);message(pending.length?'Preview only — the BIN is unchanged.':'No values would change.');grid()}
  function render(){
    const s=state(),newSource=lastOriginal!==s.original;
    if(newSource){lastOriginal=s.original;$('map-search').value='';$('map-changed').checked=false;$('map-category').replaceChildren(new Option('All categories',''),...[...new Set(s.maps.map(m=>mapCategory(m)))].sort().map(c=>new Option(c,c)));$('map-display').value='draft'}
    if(lastMaps!==s.maps){lastMaps=s.maps;$('map-category').replaceChildren(new Option('All categories',''),...[...new Set(s.maps.map(m=>mapCategory(m)))].sort().map(c=>new Option(c,c)))}
    if(lastMap!==s.m||newSource){anchor=focus=0;lastMap=s.m;pending=[];message('')}
    // Any committed edit invalidates a previously computed preview.
    pending=[];
    for(const id of ['map-search','map-category','map-changed','xdf-export'])$(id).disabled=!s.maps.length||s.loading;
    for(const id of ['map-display','map-fit','map-all','map-row','map-column','map-copy','map-graph-mode'])$(id).disabled=!s.m||s.loading;
    $('map-graph-mode').querySelector('option[value=surface]').disabled=!s.m||s.m.rows<2||s.m.columns<2;
    if(s.m&&(s.m.rows<2||s.m.columns<2))$('map-graph-mode').value='profile';
    for(const id of ['map-operation','map-factor','map-paste','ws-preview'])$(id).disabled=!editable();
    $('map-title').textContent=s.m?.display_name||'Choose a BIN to start';
    $('tune-status').textContent=s.m?`${s.identity.label} · ${s.m.rows} × ${s.m.columns} · ${s.m.element_bytes*8}-bit · ${s.m.data_address} · raw ECU values`: 'Your maps will appear here.';
    $('map-evidence').hidden=!s.m;
    if(s.m)$('map-evidence').href=`../firmware/${encodeURIComponent(s.identity.id)}/maps/${encodeURIComponent(s.m.id)}/`;
    library();grid();previewPanel();
  }
  document.addEventListener('pointerup',()=>drag=false);
  for(const id of ['map-search','map-category','map-changed'])$(id).addEventListener(id==='map-search'?'input':'change',safe(library));
  $('map-display').addEventListener('change',safe(render));$('map-fit').addEventListener('change',safe(grid));
  $('map-all').addEventListener('click',safe(()=>select(0,state().m.rows*state().m.columns-1)));
  $('map-row').addEventListener('click',safe(()=>{const m=state().m,a=Math.floor(focus/m.columns)*m.columns;select(a,a+m.columns-1)}));
  $('map-column').addEventListener('click',safe(()=>{const m=state().m,a=focus%m.columns;select(a,(m.rows-1)*m.columns+a)}));
  $('map-operation-form').addEventListener('submit',safe(e=>{e.preventDefault();preview()}));
  $('map-operation').addEventListener('change',()=>{$('map-factor-label').hidden=!['set','add','multiply'].includes($('map-operation').value);$('map-paste-label').hidden=$('map-operation').value!=='paste';pending=[];grid();message('')});
  for(const id of ['map-factor','map-paste'])$(id).addEventListener('input',()=>{if(pending.length){pending=[];grid()}});
  $('map-apply').addEventListener('click',safe(()=>{if(!pending.length||!editable())return;const p=pending;pending=[];onCommit(p);message(`${p.length} cells applied. Undo restores the entire edit.`)}));
  $('map-cancel').addEventListener('click',()=>{pending=[];grid();message('Preview cancelled.')});
  function textSelection(){const s=state(),r=rect(),mode=$('map-display').value,rows=[];for(let y=r.r0;y<=r.r1;y++){const row=[];for(let x=r.c0;x<=r.c1;x++){const i=y*s.m.columns+x,a=pending.find(p=>p.index===i)?.after??readCell(s.draft,s.base,s.m,i),o=readCell(s.original,s.base,s.m,i);row.push(mode==='original'?o:mode==='difference'?a-o:a)}rows.push(row.join('\t'))}return rows.join('\n')}
  $('map-copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(textSelection());message('Selection copied as tab-separated values.')}catch{$('map-paste-label').hidden=false;$('map-paste').value=textSelection();$('map-paste').focus();$('map-paste').select();message('Clipboard unavailable. Copy the selected text below.')}});
  $('tune-grid').addEventListener('copy',e=>{e.preventDefault();e.clipboardData.setData('text/plain',textSelection())});
  $('tune-grid').addEventListener('paste',safe(e=>{e.preventDefault();if(!editable())return;$('map-operation').value='paste';$('map-factor-label').hidden=true;$('map-paste-label').hidden=false;$('map-paste').value=e.clipboardData.getData('text/plain');preview()}));
  $('map-workspace').addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&!['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)&&['z','y'].includes(e.key.toLowerCase())){e.preventDefault();const id=e.key.toLowerCase()==='y'||e.shiftKey?'edit-redo':'edit-undo';if(!$(id).disabled)$(id).click()}});
  $('tune-grid').addEventListener('keydown',safe(e=>{
    const m=state().m;if(!m)return;
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='a'){e.preventDefault();select(0,m.rows*m.columns-1);return}
    if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();
    const r=Math.floor(focus/m.columns),c=focus%m.columns,rr=Math.max(0,Math.min(m.rows-1,r+(e.key==='ArrowDown'?1:e.key==='ArrowUp'?-1:0))),cc=Math.max(0,Math.min(m.columns-1,c+(e.key==='ArrowRight'?1:e.key==='ArrowLeft'?-1:0))),i=rr*m.columns+cc;
    select(e.shiftKey?anchor:i,i);$('tune-grid').querySelector(`[data-index="${i}"]`).focus({preventScroll:true});
  }));
  $('map-graph-mode').addEventListener('change',graph);$('map-angle').addEventListener('input',graph);new MutationObserver(graph).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
  $('xdf-export').addEventListener('click',safe(()=>{const s=state();onExport(s.identity.id+'.raw-maps.xdf',exportXdf(s.draft,s.base,s.maps,s.identity),'application/xml');message(`Exported ${s.maps.length} raw map definitions. XDF does not include checksum automation or feature patches.`)}));
  return {render};
}
