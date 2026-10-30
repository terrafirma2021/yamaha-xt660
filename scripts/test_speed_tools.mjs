import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {speedLayouts,speedState,setSpeed,speedAddresses} from '../site/assets/tools-speed.mjs';
import {matchesFeatureVariant,setFeature} from '../site/assets/tools-features.mjs';
import {baseAddress,correctStartupChecksum,verifyStartupChecksum} from '../site/assets/tools-core.mjs';
const json=p=>JSON.parse(readFileSync(new URL('../'+p,import.meta.url),'utf8'));
const catalog=json('analysis/firmware/catalog.json'),decodes=json('analysis/firmware/decode_catalog.json');
let checks=0;
for(const identity of catalog.images){
  const original=new Uint8Array(readFileSync(new URL('../'+identity.file,import.meta.url))),base=baseAddress(original),layout=speedLayouts[identity.code_family];
  assert.deepEqual(speedState(original,identity),{editable:true,enabled:true,offset:0});
  const allowed=new Set([...speedAddresses(identity),0xF7FC,0xF7FD]);
  const maps=json(decodes.images.find(i=>i.id===identity.id).maps_path);
  for(const map of maps)for(let a=Number(map.data_address);a<Number(map.end_exclusive);a++)assert.ok(!allowed.has(a),'Map overlaps patch');
  for(let offset=-20;offset<=20;offset++)for(const enabled of [true,false]){
    const draft=original.slice(),change=setSpeed(draft,identity,enabled,offset);
    assert.deepEqual(speedState(draft,identity),{editable:true,enabled,offset});
    correctStartupChecksum(draft,identity);assert.equal(verifyStartupChecksum(draft,identity).status,'pass');
    assert.ok(matchesFeatureVariant(draft,original,identity));
    draft.forEach((v,i)=>{if(v!==original[i])assert.ok(allowed.has(i+base))});
    assert.deepEqual(draft.slice(0xF800-base),original.slice(0xF800-base));
    // Existing features coexist, and repeated changes retain source recognition.
    setFeature(draft,identity,'pair',false);assert.ok(matchesFeatureVariant(draft,original,identity));
    setSpeed(draft,identity,!enabled,offset);assert.equal(speedState(draft,identity).enabled,!enabled);
    const restored=original.slice();setSpeed(restored,identity,enabled,offset);setSpeed(restored,identity,true,0);assert.deepEqual(restored,original);
    const undone=original.slice();setSpeed(undone,identity,enabled,offset);for(const c of change.changes)undone[c.address-base]=c.before;assert.deepEqual(undone,original);
    checks++;
  }
  for(const bad of [-21,21,0.5,NaN,Infinity,'2',null]){const d=original.slice();assert.throws(()=>setSpeed(d,identity,true,bad));assert.deepEqual(d,original)}
  assert.throws(()=>setSpeed(original.slice(),identity,1,0));
  // Reject every single-byte corrupt recipe, including metadata and padding.
  for(const a of speedAddresses(identity)){
    const d=original.slice();setSpeed(d,identity,true,-7);d[a-base]^=0x80;
    assert.equal(speedState(d,identity).editable,false,`Accepted corrupt byte ${a.toString(16)}`);
    assert.ok(!matchesFeatureVariant(d,original,identity));assert.throws(()=>setSpeed(d,identity,true,0));
  }
  const unknown=original.slice();unknown[0x2000-base]^=1;assert.ok(!matchesFeatureVariant(unknown,original,identity));
  const occupied=original.slice();occupied[layout.cave-base]=0;assert.equal(speedState(occupied,identity).editable,false);
}
assert.equal(speedState(null,null).editable,false);
assert.throws(()=>setSpeed(new Uint8Array(65536),{},true,0));
console.log(`Speed editor: ${checks} settings across nine BINs; map non-overlap, exact restoration/undo, strict import, corruption rejection, feature coexistence and checksum verified.`);
