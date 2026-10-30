import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {featureStates,setFeature,matchesFeatureVariant} from '../site/assets/tools-features.mjs';
import {coLayouts} from '../site/assets/tools-co.mjs';
import {matchesMapVariant} from '../site/assets/tools-map-core.mjs';
import {baseAddress,differences,correctStartupChecksum,verifyStartupChecksum} from '../site/assets/tools-core.mjs';
const root=new URL('../',import.meta.url),read=p=>readFileSync(new URL(p,root)),json=p=>JSON.parse(read(p));
const catalog=json('analysis/firmware/catalog.json'),decodes=json('analysis/firmware/decode_catalog.json');
const co=(b,i)=>featureStates(b,i).find(f=>f.id==='co-range');
let guards=0;
for(const identity of catalog.images){
  const original=new Uint8Array(read(identity.file)),draft=original.slice(),base=baseAddress(draft),f=co(draft,identity);
  const maps=json(decodes.images.find(i=>i.id===identity.id).maps_path);
  const layout=coLayouts[identity.code_family],cells=layout.descriptor+6;
  const map=maps.find(m=>parseInt(m.data_address,16)===cells);
  assert.ok(map);assert.equal(map.columns,15);assert.equal(map.rows,1);assert.equal(map.element_bytes,1);
  assert.equal(f.state,'disabled');assert.ok(f.editable);
  const edit=setFeature(draft,identity,'co-range',true);
  assert.deepEqual(edit.changes.map(c=>c.address),[cells+13,cells+14]);
  assert.equal(co(draft,identity).state,'enabled');
  assert.deepEqual([...draft.slice(cells-base,cells-base+15)],Array(15).fill(255));
  correctStartupChecksum(draft,identity);
  assert.equal(verifyStartupChecksum(draft,identity).status,'pass');
  assert.ok(differences(original,draft,base).every(c=>[cells+13,cells+14,0xF7FC,0xF7FD].includes(c.address)));
  assert.ok(matchesFeatureVariant(draft,original,identity));
  assert.ok(matchesMapVariant(draft,original,identity,maps));
  const saved=draft.slice();assert.equal(co(saved,identity).state,'enabled');
  setFeature(draft,identity,'co-range',false);correctStartupChecksum(draft,identity);
  const baseline=original.slice();correctStartupChecksum(baseline,identity);assert.deepEqual(draft,baseline);
  // The ordinary history representation can undo/redo the exact change.
  for(const c of edit.changes)draft[c.address-base]=c.after;
  correctStartupChecksum(draft,identity);assert.deepEqual(draft,saved);
  for(const c of edit.changes)draft[c.address-base]=c.before;
  correctStartupChecksum(draft,identity);assert.deepEqual(draft,baseline);
  // Every guard must fail closed, including lookup pointer, header and CO input.
  for(const [address] of f.guards){
    const bad=original.slice();bad[address-base]^=1;const before=bad.slice();
    assert.equal(co(bad,identity).editable,false);
    assert.throws(()=>setFeature(bad,identity,'co-range',true));assert.deepEqual(bad,before);
    assert.equal(matchesMapVariant(bad,original,identity,maps),false);guards++;
  }
  // Custom curve cells remain editable/reopenable as maps, never overwritten by a toggle.
  for(const index of [0,12,13,14]){
    const custom=original.slice();custom[cells+index-base]=64;
    assert.equal(co(custom,identity).editable,false);
    assert.throws(()=>setFeature(custom,identity,'co-range',true));
    assert.ok(matchesMapVariant(custom,original,identity,maps));
    assert.equal(matchesFeatureVariant(custom,original,identity),false);
  }
  const wrong={...identity,code_family:identity.code_family==='early'?'late':'early'};
  assert.equal(co(original,wrong).editable,false);
  assert.deepEqual(new Uint8Array(read(identity.file)),original);
}
assert.equal(co(null,null).editable,false);
assert.throws(()=>setFeature(new Uint8Array(65536),null,'co-range',true));
console.log(`CO override verified for ${catalog.images.length} BINs: family lookup, two-byte change, checksum, restore, history, saved-copy recognition, custom map edits and ${guards} corrupted lookup guards.`);
