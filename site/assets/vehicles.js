'use strict';
(async function(){
  const panel=document.getElementById('vehicle-context');
  if(!panel)return;
  const root=new URL(panel.dataset.root,location.href);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const controls=Object.fromEntries(['bike','year','market','ecu','image'].map(k=>[k,document.getElementById(k+'-select')]));
  const status=document.getElementById('selection-status');
  try{
    const [data,firmware,definitions,partsCatalogue,bikeRoutes]=await Promise.all(['vehicles/catalog.json','firmware/catalog.json','vehicles/definitions.json','vehicles/parts.json','vehicles/routes.json'].map(async path=>{const r=await fetch(new URL(path,root));if(!r.ok)throw new Error(path);return r.json();}));
    let profile,image;
    const route=location.pathname.slice(root.pathname.length);
    const imageRoute=route.match(/^firmware\/([^/]+)\//)?.[1];
    const images=new Map(firmware.images.map(i=>[i.id,i]));
    const models=new Map(data.models.map(m=>[m.id,m]));
    const parts=new Map(partsCatalogue.records.map(r=>[r.id,r]));
    const visibleModels=data.models.filter(m=>!m.reference_only);
    const available=p=>!!p?.firmware_ids.length&&!models.get(p.model)?.reference_only;
    const sections={overview:'',wiring:'wiring/',research:'research/',pins:'pins/',maps:'maps/',flashing:'flashing/',tune:'tune/'};
    const section=panel.dataset.section||Object.keys(sections).find(k=>route===sections[k]||route===sections[k]+'index.html');
    function modelDefault(id){return data.profiles.find(p=>p.id===models.get(id)?.default_profile&&available(p))||data.profiles.find(p=>p.model===id&&available(p));}
    function yearDefault(year){
      const candidates=data.profiles.filter(p=>p.model===profile.model&&p.year===year&&available(p));
      return candidates.find(p=>p.hardware===profile.hardware)||candidates.find(p=>p.association==='catalogue-documented'&&p.country===profile.country&&p.variant===profile.variant)||candidates.find(p=>p.association==='catalogue-documented')||candidates[0];
    }
    function options(control,entries,value){control.replaceChildren(...entries.map(([key,label,disabled=false])=>{const o=new Option(label+(disabled?' · No BIN yet':''),key);o.disabled=disabled;return o;}));control.value=value;control.disabled=entries.filter(e=>!e[2]).length<2;}
    function link(path,p=profile,i=image){
      const selected=bikeRoutes.find(r=>r.profile===p.id&&r.firmware===i?.id);
      const targetSection=Object.keys(sections).find(k=>path===sections[k]||path===sections[k]+'index.html')||(path.startsWith('bikes/')?section:null);
      if(targetSection&&selected){
        path=targetSection==='maps'&&i?.decoded_map_count&&!i.shared_map_count?'firmware/'+i.id+'/maps/':selected.path+sections[targetSection];
      }
      return new URL(path,root).href;
    }
    function readState(){
      const q=new URLSearchParams(location.search);
      let saved={};try{saved=JSON.parse(localStorage.getItem('yamaha-research-context')||'{}');}catch{}
      const explicit=q.has('profile')||q.has('firmware')||!!panel.dataset.profile;
      const pid=q.get('profile')||panel.dataset.profile||(!explicit?saved.profile:null);
      const iid=imageRoute||q.get('firmware')||panel.dataset.firmware||(!explicit?saved.firmware:null);
      profile=data.profiles.find(p=>p.id===pid);
      if(profile&&!available(profile))profile=modelDefault(profile.model);
      if(iid&&(!profile||!profile.firmware_ids.includes(iid)))profile=data.profiles.find(p=>p.firmware_ids.includes(iid));
      profile=profile||data.profiles.find(p=>p.id===data.default_profile);
      image=images.get(profile.firmware_ids.includes(iid)?iid:profile.firmware_ids[0])||null;
    }
    function sources(){return profile.source_ids.map(id=>data.sources.find(s=>s.id===id));}
    function sourceList(){return '<ul class="source-list">'+sources().map(s=>`<li><h3><a href="${esc(s.url)}">${esc(s.title)} ↗</a></h3><p>${esc(s.claim)}</p><small>${esc(s.locator)}</small></li>`).join('')+'</ul>';}
    function definitionList(){
      const key=image?.id||'';
      const selected=definitions.filter(d=>image?.map_catalog==='primary'?d.source_path.startsWith('xt 660 r/'):/2c1-10/.test(key)?d.source_path.includes('2012-2016'):/5vk-(1x|11)/.test(key)?d.source_path.includes('2008'):false);
      return selected.length?'<p>Candidate definitions selected by source naming. Address, shape and physical-unit validation are separate checks. No XDF formula is treated as ground truth.</p><ul class="definition-list">'+selected.map(d=>`<li><a href="https://github.com/terrafirma2021/yamaha-xt660/blob/main/${d.stored_path.split('/').map(encodeURIComponent).join('/')}">${esc(d.source_path)}</a> · ${d.sha256.slice(0,12)}…</li>`).join('')+'</ul>':'<p>No definition is assigned to this firmware. Existing XDFs are not automatically transferred.</p>';
    }
    function overview(hardware=false){
      const m=models.get(profile.model),shared=image?.decoded_map_count||0;
      const record=parts.get(profile.parts_record);
      const photo=m.photo;

      const photoMarkup=`<figure class="model-photo"><img class="vehicle-art" src="${new URL(photo.file,root)}" width="${photo.width}" height="${photo.height}" alt="Yamaha ${esc(m.name)} — ${esc(photo.year)} model reference" loading="lazy"><figcaption>${esc(photo.caption)} <a href="${esc(photo.source)}">Photo source ↗</a></figcaption></figure>`;
      const roleNames={ecu:'Engine control unit',harness:'Main wiring harness',coolant:'Coolant temperature sensor',pressure:'Pressure sensor',intake_air:'Intake air temperature sensor',speed:'Speed sensor',oxygen:'Oxygen sensor',lean_angle:'Lean-angle sensor'};
      const partMarkup=record?`<h3>Catalogue parts for ${esc(record.model_code)} / ${esc(record.country)}</h3><p>Original references and replacement parts are separate. These are component identities; they do not establish connector-to-MCU continuity or physical scaling.</p><div class="part-cards">${record.parts.map(p=>`<article><span class="kicker">${esc(roleNames[p.role]||p.role)}</span><strong>${esc(p.replaces||p.listed_part)}</strong>${p.replaces?`<p>Listed replacement: <code>${esc(p.listed_part)}</code></p>`:'<p>Listed part; no replacement relationship shown.</p>'}<a href="${esc(p.source_url)}">${esc(p.assembly)} · item ${esc(p.reference)} ↗</a></article>`).join('')}</div>`:'';
      return `<div class="vehicle-summary"><div><div class="kicker">${esc(m.style)} / ${esc(profile.display_status||profile.association.replaceAll('-',' '))}</div><h2>${esc(m.name)}<br>${esc(profile.year)}</h2><p>${esc(profile.notes)}</p><dl class="vehicle-specs"><dt>Market</dt><dd>${esc(profile.market)}</dd><dt>ECU</dt><dd>${esc(profile.ecu)}</dd>${record?`<dt>Model code / variant</dt><dd>${esc(record.model_code)} · ${esc(record.variant)}</dd><dt>Harness reference</dt><dd>${esc(record.parts.filter(p=>p.role==='harness').map(p=>p.replaces?`${p.replaces} → ${p.listed_part} replacement`:p.listed_part).join('; '))}</dd>`:''}<dt>Firmware</dt><dd>${esc(image?.label||'No BIN available')}${image?.variant?` · ${esc(image.variant)}`:''}</dd><dt>Oxygen sensor</dt><dd>${esc(profile.oxygen)}</dd></dl></div><div>${photoMarkup}<div class="source-card"><strong>${image?'Firmware identity recorded':'Documentation profile'}</strong><p>${image?`${image.size.toLocaleString()} bytes · boot ${esc(image.boot_status)}<br><code>${image.sha256.slice(0,20)}…</code>`:'No local firmware has been matched to this model/ECU. Maps and MCU pin claims are not inherited.'}</p></div></div></div>
      <div class="coverage-tiles"><div><small>CALIBRATION</small><strong>${shared?shared+' extracted layouts':'No reviewed catalogue'}</strong><small>${shared?'Cells and axes are extracted for this BIN. Physical scaling is still incomplete.':'This firmware needs its own map/consumer review.'}</small></div><div><small>HARDWARE</small><strong>${image?image.code_family==='late'?'Later application pin review':'Early application pin review':'Separate applicability'}</strong><small>${image?'Instruction bytes checked per BIN; manual connector and physical fitment remain separate.':'Use the references for this profile. No BIN-specific pin review is assigned.'}</small></div><div><small>DEFINITIONS</small><strong>${image?'Source candidates':'None matched'}</strong><small>XDF presence does not establish correct addressing, units or ECU compatibility.</small></div></div>
      <div class="profile-actions"><a href="${link(image?.decoded_map_count&&!image.shared_map_count?'firmware/'+image.id+'/maps/':'maps/')}">Maps &amp; curves ↗</a><a href="${link('wiring/')}">Wiring &amp; sensors ↗</a><a href="${link(image?'firmware/'+image.id+'/':'firmware/')}">Firmware record ↗</a><a href="${link('research/')}">Research ↗</a></div>
      ${hardware?`${partMarkup}<h3>Wiring and MCU applicability</h3><p>${image?'The pin explorer checks this BIN’s code and the conditional MC9S12T64 package. Early and later applications have separate GPIO assignments and 26- / 34-position manual references. Exact hardware fitment, connector orientation and board continuity remain separately qualified.':'No BIN-specific pin review is assigned to this profile.'}</p>${image?`<p><a href="${link('pins/')}">Open this ECU’s MCU and connector explorer ↗</a></p>`:''}${profile.hardware==='brazil-2c1-10'?'<p>The supplied 34-position flashing sketch marks 3 / 7 / 12 for power, ground and K-line. Those three positions correlate with the later Yamaha drawing after horizontal reflection; the view convention is unconfirmed. Its numbering does not transfer to the early 26-position reference. See the pin explorer for the comparison.</p>':''}`:''}
      <details ${hardware?'open':''}><summary>Sources and model/year evidence</summary>${profile.label_evidence?`<p>${esc(profile.label_evidence)}</p>`:''}${sourceList()}</details>`;
    }
    function render(push=false){
      if(section==='maps'&&image?.decoded_map_count&&!image.shared_map_count){location.replace(link('firmware/'+image.id+'/maps/'));return;}
      if(location.search&&(new URLSearchParams(location.search).has('profile')||new URLSearchParams(location.search).has('firmware'))){
        const clean=section?link(sections[section]||'index.html'):new URL(route,root).href;
        if(section){location.replace(clean+location.hash);return;}
        history.replaceState(null,'',clean+location.hash);
      }
      const m=models.get(profile.model),sameModel=data.profiles.filter(p=>p.model===profile.model);
      const years=[...new Set(sameModel.map(p=>p.year))].sort((a,b)=>(parseInt(a)||9999)-(parseInt(b)||9999));
      const sameYear=sameModel.filter(p=>p.year===profile.year),markets=[...new Set(sameYear.map(p=>p.market))];
      const sameMarket=sameYear.filter(p=>p.market===profile.market);
      options(controls.bike,visibleModels.map(m=>[m.id,m.name,!modelDefault(m.id)]),profile.model);
      options(controls.year,years.map(y=>[y,y,!sameModel.some(p=>p.year===y&&available(p))]),profile.year);
      options(controls.market,markets.map(v=>[v,v,!sameYear.some(p=>p.market===v&&available(p))]),profile.market);
      options(controls.ecu,sameMarket.map(p=>[p.id,p.ecu,!available(p)]),profile.id);
      options(controls.image,profile.firmware_ids.map(id=>[id,images.get(id).label+' · '+images.get(id).variant]),image?.id||'');
      status.textContent=`${m.name} · ${profile.year} · ${profile.market} · ${profile.display_status||profile.association.replaceAll('-',' ')}. ${image?.decoded_map_count?'Application code and map bytes checked; physical-unit and hardware limits still apply.':'No reviewed map catalogue is assigned.'}`;
      try{localStorage.setItem('yamaha-research-context',JSON.stringify({profile:profile.id,firmware:image?.id||null}));}catch{}
      document.querySelectorAll('[data-bike]').forEach(a=>a.setAttribute('aria-current',String(a.dataset.bike===profile.model)));
      for(const id of ['vehicle-overview','vehicle-research']){const el=document.getElementById(id);if(el)el.innerHTML=overview();}
      const hardware=document.getElementById('vehicle-hardware');if(hardware)hardware.innerHTML=overview(true);
      const defs=document.getElementById('vehicle-definitions');if(defs)defs.innerHTML=definitionList();
      const allowed=!!image?.shared_map_count;
      document.querySelectorAll('[data-study]').forEach(el=>{
        const isHardware=el.dataset.study==='hardware';
        el.hidden=el.dataset.study==='pins'?!image:!(allowed&&(!isHardware||profile.hardware==='early-owner'));
        let notice=el.previousElementSibling;
        if(!notice?.classList.contains('scope-unavailable')){notice=document.createElement('section');notice.className='scope-unavailable';el.before(notice);}
        notice.hidden=!el.hidden;
        notice.innerHTML=`<h2>${isHardware?'No verified pin explorer':'Original-calibration document'} for this selection</h2><p>${esc(m.name)} · ${esc(profile.year)} · ${esc(profile.ecu)}. ${isHardware?'Connector cavities and MCU pins must be traced for this exact hardware.':'This document describes the original calibration. Use this BIN’s own map catalogue and family analysis for its extracted values.'}</p><p>${image?.decoded_map_count?`<a href="${link('firmware/'+image.id+'/maps/')}">Maps for this BIN ↗</a> · <a href="${link('docs/firmware/FAMILY_DECODING.html')}">Application-family analysis ↗</a> · `:''}<a href="${link('wiring/')}">Selected profile and sources ↗</a> · <a href="${link('index.html')}">Motorcycle overview ↗</a></p><p><a href="${link(route,data.profiles.find(p=>p.id===data.default_profile),images.get(firmware.primary_id))}">Switch explicitly to the 2005 XT660X study ↗</a></p>`;
      });
      document.querySelectorAll('[data-firmware-card]').forEach(el=>{el.hidden=!document.getElementById('all-firmware')?.checked&&!profile.firmware_ids.includes(el.dataset.firmwareCard);});
      const libraryStatus=document.getElementById('library-status');if(libraryStatus)libraryStatus.textContent=profile.firmware_ids.length?`${profile.firmware_ids.length} records associated with this profile. Association may be filename-based; see each record.`:'No firmware assigned to this profile. The full dataset remains available below.';
      document.documentElement.classList.remove('scope-pending');
      document.dispatchEvent(new CustomEvent('vehiclechange',{detail:{profile:profile.id,firmware:image?.id||null}}));
    }
    function change(p,i){
      if(!available(p))return;
      profile=p;image=images.get(i||p.firmware_ids[0]);
      try{localStorage.setItem('yamaha-research-context',JSON.stringify({profile:profile.id,firmware:image.id}));}catch{}
      if(imageRoute){location.href=link('firmware/'+image.id+(route.includes('/maps/')?'/maps/':'/'));return;}
      if(section){location.href=link(sections[section]||'index.html');return;}
      render();
    }
    controls.bike.addEventListener('change',()=>change(modelDefault(controls.bike.value)));
    controls.year.addEventListener('change',()=>change(yearDefault(controls.year.value)));
    controls.market.addEventListener('change',()=>change(data.profiles.find(p=>p.model===profile.model&&p.year===profile.year&&p.market===controls.market.value&&available(p))));
    controls.ecu.addEventListener('change',()=>change(data.profiles.find(p=>p.id===controls.ecu.value)));
    controls.image.addEventListener('change',()=>change(profile,controls.image.value));
    document.getElementById('all-firmware')?.addEventListener('change',()=>render());
    document.addEventListener('click',event=>{
      const a=event.target.closest('a');if(!a)return;
      if(a.dataset.bike){event.preventDefault();change(modelDefault(a.dataset.bike));return;}
      const u=new URL(a.href);if(u.origin!==root.origin||!u.pathname.startsWith(root.pathname))return;
      if(!u.pathname.endsWith('/')&&!u.pathname.endsWith('.html'))return;
      if(u.pathname===location.pathname&&u.hash)return;
      // Generated context links already identify their target. Global navigation is scoped here.
      if(u.pathname.slice(root.pathname.length).startsWith('bikes/'))return;
      a.href=link(u.pathname.slice(root.pathname.length))+u.hash;
    });
    window.addEventListener('popstate',()=>{readState();render();});
    readState();render();
  }catch(error){
    status.textContent='The vehicle catalogue could not be loaded. Reload this page. The original study below is explicitly scoped to the 2005 XT660X dump.';
    // A failed catalogue load must not show primary data under another profile.
    document.querySelectorAll('[data-study]').forEach(el=>el.hidden=true);
    document.documentElement.classList.remove('scope-pending');
    console.error(error);
  }
})();
