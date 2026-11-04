import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto, createHash} from 'node:crypto';
import {connectionForSelection, connectorSvg, kklSvg, checkFlashFile, prepareChecksumCopy} from '../flasher/core/flashing-core.mjs';
import {baseAddress, readCell, editCell, correctStartupChecksum} from '../flasher/core/tools-core.mjs';
if(!globalThis.crypto)globalThis.crypto=webcrypto;
const read=p=>readFileSync(new URL('../'+p,import.meta.url));
const json=p=>JSON.parse(read(p));
const data=json('_site/flashing/connections.json'),catalog=json('_site/firmware/catalog.json');
const reference=async i=>new Uint8Array(read(i.file));
const maps=async i=>json('_site/firmware/layouts/'+i.id+'.json');
let profiles=0;
for(const [pid,p] of Object.entries(data.profiles))for(const id of p.firmware_ids){
  const i=catalog.images.find(i=>i.id===id),selected=connectionForSelection(data,pid,i);
  assert(selected);assert.equal(selected.family.id,i.code_family);profiles++;
  assert.equal(selected.family.positions,i.code_family==='early'?26:34);
}
assert.equal(connectionForSelection(data,'unknown',catalog.images[0]),null);
assert.equal(connectionForSelection(data,'xt660x-2005-owner',catalog.images.find(i=>i.code_family==='late')),null);
for(const [name,f] of Object.entries(data.families)){
  assert.equal(f.source.sha256,createHash('sha256').update(read(f.source.file)).digest('hex'));
  assert.equal(f.slots.length,f.positions);
  assert.equal(new Set(f.slots.map(s=>s.position)).size,f.positions);
  const active=f.slots.filter(s=>s.signal);
  assert.deepEqual(active.map(s=>[s.position,s.signal,s.wire]),[['U03','power','R'],['U07','ground','B/W'],['U12','kline','Y/L']]);
  assert.deepEqual(active.map(s=>s.manual_position),name==='early'?['U11','U07','U02']:['U15','U11','U06']);
  const svg=connectorSvg(f);
  assert.equal((svg.match(/data-position=/g)||[]).length,f.positions);
  assert.equal((svg.match(/data-signal=/g)||[]).length,3);
  assert(svg.includes(`${f.positions}-position ECU connector`));
}
assert(kklSvg().includes('16 · +12V'));assert(kklSvg().includes('4 / 5 · GND'));assert(kklSvg().includes('7 · K-line'));
for(const i of catalog.images){
  const bytes=await reference(i),before=bytes.slice();
  const result=await checkFlashFile(bytes,catalog,i.id,reference,maps);
  assert.equal(result.identity.id,i.id);assert(result.selected_layout_matches);
  assert.equal(result.flash_ready,false);assert.equal(result.hardware_verified,false);
  assert.equal(result.boot_reference_matches,!result.boot.startsWith('FF'));
  assert.deepEqual(bytes,before,'Flashing inspection must preserve original bytes');
  const fixed=await prepareChecksumCopy(bytes,catalog,i.id,reference,maps);
  assert.equal(fixed.checksum.status,'pass');assert.deepEqual(bytes,before);
  for(let offset=0;offset<bytes.length;offset++)if(fixed.bytes[offset]!==bytes[offset])assert([0xF7FC,0xF7FD].includes(offset+i.base_address));

}
const i=catalog.images.find(i=>i.id==='xt660-2004-2006-companion');
const edited=await reference(i),layout=(await maps(i))[0],base=baseAddress(edited);
const value=readCell(edited,base,layout,0);editCell(edited,base,layout,0,value===0?1:value-1);correctStartupChecksum(edited,i);
const before=edited.slice(),matched=await checkFlashFile(edited,catalog,i.id,reference,maps);
assert.equal(matched.identity_match,'recognised map/feature-edited layout');assert(matched.selected_layout_matches);assert.equal(matched.checksum.status,'pass');assert.deepEqual(edited,before);
const wrong=await checkFlashFile(edited,catalog,catalog.images.find(i=>i.code_family==='late').id,reference,maps);
assert.equal(wrong.selected_layout_matches,false);
const unknown=edited.slice();unknown[0xF900-base]^=1;
const rejected=await checkFlashFile(unknown,catalog,i.id,reference,maps);
assert.equal(rejected.identity,null);assert.equal(rejected.boot_reference_matches,false);assert.equal(rejected.checksum.status,'unverified');
await assert.rejects(()=>checkFlashFile(new Uint8Array(100),catalog,i.id,reference,maps));
const uncorrected=await reference(i);editCell(uncorrected,base,layout,0,value===0?1:value-1);
const uncorrectedBefore=uncorrected.slice();
const fixed=await prepareChecksumCopy(uncorrected,catalog,i.id,reference,maps);
assert.equal(fixed.checksum.status,'pass');assert.deepEqual(uncorrected,uncorrectedBefore);
assert.equal(readCell(fixed.bytes,base,layout,0),value===0?1:value-1);
await assert.rejects(()=>prepareChecksumCopy(uncorrected,catalog,catalog.images.find(i=>i.code_family==='late').id,reference,maps));
await assert.rejects(()=>prepareChecksumCopy(unknown,catalog,i.id,reference,maps));
const xdf=read('_site/xdf/index.html').toString(),flash=read('_site/flashing/index.html').toString();
for(const html of [xdf,flash])for(const id of ['feature-list','map-workspace','map-apply','edit-undo','tune-grid'])assert(!html.includes('id="'+id+'"'));
assert(xdf.includes('Download XDF'));assert(flash.includes('Bench connections'));
for(const id of ['ecu-connect','read-ecu','flash-ecu','verify-readback','flash-bin-file'])assert(!flash.includes(`id="${id}"`));
console.log(`Flashing checks passed: ${profiles} profile/BIN selections, two connectors, nine immutable inputs, edited/unknown files and guarded checksum copies.`);
