import {baseAddress, sha256, inspect, verifyStartupChecksum} from './tools-core.mjs';
import {matchesFeatureVariant} from './tools-features.mjs';
import {matchesMapVariant} from './tools-map-core.mjs';

export const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const signalNames = {power:'+12V', ground:'GND', kline:'K-line'};

export function connectionForSelection(data, profileId, image) {
  const profile = data.profiles[profileId];
  if (!profile || !image || !profile.firmware_ids.includes(image.id) || profile.family !== image.code_family) return null;
  const family = data.families[profile.family];
  return family ? {profile, family} : null;
}

// Same two-row connector language as the MCU explorer, oriented to each flash source.
export function connectorSvg(family) {
  const width = family.columns * 75 + 64;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} 225" role="img" aria-label="${family.positions}-position ECU connector; upper 3 power, upper 7 ground, upper 12 K-line">
    <rect class="connector-frame" width="${width}" height="225" rx="8"/>
    <path class="connector-latch" d="M${width/2-25} 47V32H${width/2+25}V47"/>
    ${family.slots.map(s => {
      const x=32+(s.column-1)*75, y=s.row==='Upper'?52:130;
      return `<g class="flash-slot ${s.signal?'signal-'+s.signal:''} ${s.wire?'':'empty'}" data-position="${s.position}" data-manual="${s.manual_position}" ${s.signal?`data-signal="${s.signal}"`:''}>
        <title>${escapeHTML(s.position+' · '+(s.wire||'cross-marked')+(s.signal?' · '+signalNames[s.signal]:'')+' · manual '+s.manual_position)}</title>
        <rect x="${x}" y="${y}" width="72" height="68" rx="4"/>
        <text class="slot-coordinate" x="${x+36}" y="${y+22}" text-anchor="middle">${s.position}</text>
        <text class="slot-wire" x="${x+36}" y="${y+51}" text-anchor="middle">${escapeHTML(s.wire||'×')}</text></g>`;
    }).join('')}</svg>`;
}

export function kklSvg() {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1040 280" role="img" aria-label="Connection schematic: external 12 volt supply to ECU power and OBD 16; shared ground to ECU and OBD 4 or 5; ECU K-line to OBD 7. USB goes to the computer.">
  <text class="kkl-label" x="24" y="26">ECU CONNECTIONS</text><text class="kkl-label" x="762" y="26">KKL / OBD TERMINALS</text>
  <rect class="kkl-box" x="12" y="44" width="244" height="212" rx="8"/>
  <rect class="kkl-box" x="748" y="44" width="280" height="212" rx="8"/>
  ${[['power',80,'+12V · U03','16 · +12V'],['ground',150,'GND · U07','4 / 5 · GND'],['kline',220,'K-line · U12','7 · K-line']].map(([signal,y,left,right])=>`
    <g class="signal-${signal}"><path class="connection-wire" d="M256 ${y}H748"/><circle class="wire-end" cx="256" cy="${y}" r="5"/><circle class="wire-end" cx="748" cy="${y}" r="5"/>
    <text class="terminal-text" x="32" y="${y+6}">${left}</text><text class="terminal-text" x="770" y="${y+6}">${right}</text></g>`).join('')}
  <rect class="supply-label" x="352" y="62" width="300" height="36" rx="4"/><text class="supply-text" x="502" y="86" text-anchor="middle">Fused external +12V supply</text>
  <rect class="supply-label" x="352" y="132" width="300" height="36" rx="4"/><text class="supply-text" x="502" y="156" text-anchor="middle">Shared supply negative / ground</text>
  <text class="kkl-footer" x="888" y="278" text-anchor="middle">USB → computer</text></svg>`;
}

export async function checkFlashFile(bytes, catalog, selectedId, loadReference, loadMaps) {
  baseAddress(bytes); // Reject partial/oversized files without padding.
  const digest = await sha256(bytes);
  const exact = catalog.images.find(i => i.sha256 === digest) || null;
  const candidates = catalog.images.filter(i => i.size === bytes.length);
  const matches = [];
  for (const i of candidates) {
    if (i === exact) { matches.push(i); continue; }
    const reference = await loadReference(i);
    if (matchesFeatureVariant(bytes, reference, i) || matchesMapVariant(bytes, reference, i, await loadMaps(i))) matches.push(i);
  }
  const selected = matches.find(i => i.id === selectedId) || null;
  const identity = exact || selected || matches[0] || null;
  return {
    sha256:digest, identity, identity_match:exact?'exact registered hash':identity?'recognised map/feature-edited layout':'unregistered',
    matching_reference_ids:matches.map(i=>i.id), selected_reference:selectedId,
    selected_layout_matches:!!selected, checksum:verifyStartupChecksum(bytes, identity),
    ...inspect(bytes), boot_reference_matches:!!identity && inspect(bytes).boot.startsWith('Populated'),
    flash_ready:false, hardware_verified:false,
  };
}
