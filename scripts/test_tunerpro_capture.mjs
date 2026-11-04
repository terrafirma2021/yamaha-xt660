// Recheck recorded native TunerPro observations. This does not launch TunerPro.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {sha256, differences, readCell, verifyStartupChecksum, correctStartupChecksum} from '../site/assets/tools-core.mjs';
import {exportXdf, matchesMapVariant} from '../site/assets/tools-map-core.mjs';

const read=p=>readFileSync(new URL('../'+p,import.meta.url));
const json=p=>JSON.parse(read(p));
const registry=json('analysis/firmware/catalog.json');
const decodes=json('analysis/firmware/decode_catalog.json');
const observations=json('analysis/firmware/tunerpro_capture.json');
let copiedCells=0;
for(const observed of observations.captures){
  const identity=registry.images.find(i=>i.id===observed.identity);
  assert(identity,'Captured image must still be registered');
  const original=new Uint8Array(read(identity.file));
  const maps=json(decodes.images.find(i=>i.id===identity.id).maps_path);
  assert.equal(await sha256(original),identity.sha256);
  assert.equal(await sha256(original),observed.sha256.original);
  const xdf=exportXdf(original,identity.base_address,maps,identity);
  assert.equal(await sha256(new TextEncoder().encode(xdf)),observed.sha256.xdf,
    'Export changed since native capture: review/repeat the native check');
  const edited=original.slice(),offsets=new Set();
  for(const d of observed.byte_changes){
    assert.equal(d.address,d.file_offset+identity.base_address);
    assert(d.file_offset>=0&&d.file_offset<edited.length);
    assert(!offsets.has(d.file_offset));offsets.add(d.file_offset);
    assert.equal(edited[d.file_offset],d.before);
    assert(Number.isInteger(d.after)&&d.after>=0&&d.after<=255);
    edited[d.file_offset]=d.after;
  }
  // The saved file's measured digest binds the compact byte-difference record.
  assert.equal(await sha256(edited),observed.sha256.edited);
  assert.equal(edited.length,observed.bytes);
  assert(matchesMapVariant(edited,original,identity,maps));
  const changed=[];let cells=0;
  for(const m of maps)for(let n=0;n<m.rows*m.columns;n++){
    const before=readCell(original,identity.base_address,m,n);
    const after=readCell(edited,identity.base_address,m,n);cells++;
    if(before!==after)changed.push({map:m.id,row:Math.floor(n/m.columns)+1,column:n%m.columns+1,before,after});
  }
  assert.equal(cells,observed.compared_cells);
  assert.deepEqual(changed,observed.changed_cells);
  assert.deepEqual(verifyStartupChecksum(original,identity),observed.original_checksum);
  assert.deepEqual(verifyStartupChecksum(edited,identity),observed.edited_checksum);
  if(observed.native_grid){
    const grid=observed.native_grid,m=maps.find(m=>m.id===grid.map);
    assert.equal(m.rows,grid.rows);assert.equal(m.columns,grid.columns);
    const rows=Array.from({length:m.rows},(_,r)=>Array.from({length:m.columns},(_,c)=>
      readCell(edited,identity.base_address,m,r*m.columns+c)).join('\t'));
    const text=rows.join('\n')+'\n';
    assert.equal(await sha256(new TextEncoder().encode(text)),grid.normalized_tsv_sha256,
      'Recorded clipboard values differ from the reconstructed native BIN');
    assert.equal(grid.compared_cells,m.rows*m.columns);assert.equal(grid.mismatches,0);
    copiedCells+=grid.compared_cells;
  }
  const corrected=edited.slice(),result=correctStartupChecksum(corrected,identity);
  assert.deepEqual(result,observed.corrected_checksum);
  assert.deepEqual(differences(edited,corrected,identity.base_address),observed.correction_changes);
  assert.equal(await sha256(corrected),observed.sha256.corrected);
  assert(matchesMapVariant(corrected,original,identity,maps));
}
console.log(`Recorded TunerPro checks consistent: ${observations.captures.length} native saved BIN(s), ${copiedCells} copied grid cells, byte differences, export identity and checksum correction. No GUI is run by this test.`);
