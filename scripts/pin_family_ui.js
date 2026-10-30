// Per-image overlay for the accepted package/connector explorer. Selection is
// supplied by vehicles.js; map equality never decides hardware applicability.
const pinPanel=document.getElementById('vehicle-context');
let pinAuditPromise, pinSelection=0, pinDrawingUrl;
function drawConnector(connector){
 const columns=Math.max(...connector.slots.map(s=>s.column)),width=columns*75+64;
 document.querySelector('.connector-scroll').innerHTML=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} 225" role="img" aria-label="${connector.slots.length}-position manual reference">
 <rect width="${width}" height="225" rx="8" fill="#122631"/>
 <path d="M${width/2-25} 47V32H${width/2+25}V47" fill="none" stroke="#9eb5c2" stroke-width="3"/>
 ${connector.slots.map(s=>{const x=32+(s.column-1)*75,y=s.row==='Upper'?52:130;return `<g class="connector-slot" data-connector="${s.position}" role="button" tabindex="0" aria-label="${esc(s.position+': '+(s.wire||'cross-marked')+', '+s.role)}"><rect x="${x}" y="${y}" width="72" height="68" rx="4" fill="${s.wire?'#274654':'#1b303b'}" stroke="#7895a6"/><text x="${x+36}" y="${y+22}" text-anchor="middle" fill="#a8c3d1" font-family="sans-serif" font-size="13">${s.position}</text><text x="${x+36}" y="${y+51}" text-anchor="middle" fill="white" font-family="sans-serif" font-size="20">${esc(s.wire||'×')}</text></g>`}).join('')}</svg>`;
}
function drawPinAudit(audit,image){
 const family=audit.families[image.family];
 data={...data,pins:structuredClone(family.pins),ecu_connector:family.connector,sources:audit.sources};
 for(const p of data.pins)p.check=image.checks.find(c=>c.pin===p.pin);
 const scope=document.getElementById('pin-scope');
 scope.dataset.firmware=image.id;scope.dataset.family=image.family;
 scope.innerHTML=`<div class="eyebrow">Selected firmware / ${esc(image.family)} application</div><h2>${esc(image.label)}</h2><p>${esc(image.variant)} · Boot ${esc(image.boot_status)} · <code>${esc(image.sha256.slice(0,16))}…</code></p><div class="pin-checks"><div><strong>${image.verified_code_pins} / 80</strong><span>Positions with instruction bytes checked in this BIN</span></div><div><strong>80 / 80</strong><span>Package labels checked against the MC9S12T64 datasheet</span></div><div><strong>Physical match open</strong><span>Chip marking and connector-to-board continuity unconfirmed</span></div></div>`;
 document.getElementById('pin-eyebrow').textContent='Firmware hardware reference / '+image.label;
 document.getElementById('pin-intro').textContent='Select a connector position or MCU pin to inspect this BIN’s code evidence. The manual drawing is a reference for this application family; it does not certify the physical ECU fitted to every listed motorcycle.';
 const c=data.ecu_connector,columns=c.slots.length/2;
 document.getElementById('connector-intro').innerHTML=`<strong>${c.slots.length} drawing positions</strong> · ${c.slots.filter(s=>s.wire).length} wire labels · ${c.slots.filter(s=>!s.wire).length} crosses. <a href="${esc(c.source_url)}#page=${c.source_pdf_pages.at(-1)}">${esc(c.source_title)} ↗</a><br>${esc(c.target_scope)}`;
 document.getElementById('connector-coordinates').textContent=`U01–U${columns} / L01–L${columns}: upper/lower row counted left to right as drawn. Research coordinates, not OEM cavity numbers. Mating-face versus wire-entry view is not specified.`;
 drawConnector(c);
 const colors={sensor:'#147d92',digital:'#147d92',actuator:'#c86027',communication:'#5863bd',internal:'#728092',power:'#b63d57',unresolved:'#aab4bd'};
 document.querySelectorAll('.diagram .pin').forEach(el=>{const p=data.pins[Number(el.dataset.pin)-1];el.querySelector('rect').setAttribute('fill',colors[p.category]||colors.internal);el.setAttribute('aria-label',`Package pin ${p.pin}: ${p.signal}, ${p.role}`);const title=el.querySelector('title');if(title)title.textContent=p.role;});
 const title=document.querySelector('.diagram svg text');
 if(title)title.textContent=`${image.label} · conditional MCU package reference`;
 const drawing=document.querySelector('.diagram svg').cloneNode(true);
 drawing.querySelectorAll('.selected').forEach(el=>el.classList.remove('selected'));
 if(pinDrawingUrl)URL.revokeObjectURL(pinDrawingUrl);
 pinDrawingUrl=URL.createObjectURL(new Blob([drawing.outerHTML],{type:'image/svg+xml'}));
 const download=document.getElementById('pin-drawing');download.href=pinDrawingUrl;download.download=image.id+'-mcu-pins.svg';
 document.getElementById('family-notes').textContent=image.family==='early'?'Early code: PAIR uses PP1. The ordinary ADC scan skips AN7; PE2/PE3 cycle during banked acquisition. Oxygen software exists but stock variant 9 leaves feedback inactive.':'Later code: PAIR uses PP0; PP1 drives a diagnostic/fault-pattern output. AN7 is sampled, PE2/PE3 are initialized low, and PT7 is an auxiliary GPIO with an unresolved external destination. The manual adds an oxygen-signal and heater circuit.';
 const flash=audit.flash_comparison;
 document.getElementById('flash-comparison').innerHTML=`<div class="eyebrow">Flash-tool connector cross-check</div><h2>${flash.positions}-position flashing sketch</h2><p>${esc(image.family==='early'?flash.early_finding:flash.finding)}</p><details><summary>Compare sketch positions with the manual</summary><p>${esc(flash.label)}. ${esc(flash.source_numbering)}</p><div class="scroll"><table><thead><tr><th>Sketch label</th><th>Manual coordinate after reflection</th><th>Wire / function</th></tr></thead><tbody>${flash.correlations.map(r=>`<tr><td>${r.sketch_pin}</td><td>${r.manual_position}</td><td>${esc(r.wire)} · ${esc(r.role)}</td></tr>`).join('')}</tbody></table></div><p>${esc(flash.finding)}</p><p>${esc(flash.route_status)}</p><p><a href="https://github.com/terrafirma2021/yamaha-xt660/blob/main/${flash.source.split('/').map(encodeURIComponent).join('/')}">Original flashing sketch ↗</a></p></details>`;
 document.getElementById('sources').innerHTML=data.sources.map(s=>`<li><a href="${esc(s.url)}">${esc(s.title)}</a>, PDF pages ${s.pdf_pages.join(', ')}</li>`).join('');
 const root=new URL(pinPanel.dataset.root,location.href);
 document.getElementById('pin-structured').href=new URL('pins/pin_audit.json',root);
 renderRows();selectPin(80);
 document.getElementById('pin-explorer').hidden=false;
 scope.setAttribute('aria-busy','false');
}
async function loadPinFamily(firmware){
 const request=++pinSelection,scope=document.getElementById('pin-scope');
 scope.setAttribute('aria-busy','true');scope.textContent='Loading pin evidence for the selected BIN…';
 delete scope.dataset.firmware;
 document.getElementById('pin-explorer').hidden=true;
 try{
  if(!pinAuditPromise){const root=new URL(pinPanel.dataset.root,location.href);pinAuditPromise=fetch(new URL('pins/pin_audit.json',root)).then(r=>{if(!r.ok)throw Error('Pin evidence request failed');return r.json()}).catch(e=>{pinAuditPromise=null;throw e});}
  const audit=await pinAuditPromise;if(request!==pinSelection)return;
  const image=audit.images.find(i=>i.id===firmware);if(!image)throw Error('No pin review is registered for this BIN');
  drawPinAudit(audit,image);
 }catch(error){if(request!==pinSelection)return;scope.setAttribute('aria-busy','false');scope.innerHTML='<h2>Pin evidence could not be loaded</h2><p>'+esc(error.message)+'. Reload the page to retry. No other ECU’s pinout is substituted.</p>';}
}
if(pinPanel){
 document.getElementById('pin-explorer').hidden=true;
 document.addEventListener('vehiclechange',event=>loadPinFamily(event.detail.firmware));
 document.addEventListener('keydown',event=>{const el=event.target.closest('.connector-slot');if(el&&(event.key==='Enter'||event.key===' ')){event.preventDefault();selectConnector(el.dataset.connector)}});
}else document.getElementById('pin-scope').textContent='Standalone early-image reference. Use the website selector for per-BIN checks and the later connector.';
