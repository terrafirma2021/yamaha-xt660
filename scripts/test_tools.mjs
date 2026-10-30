import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve,dirname} from 'node:path';
import {webcrypto} from 'node:crypto';
import {sha256,baseAddress,inspect,wordSum,differences,readCell,editCell,parseHex,bootReadPreview,READ_LENGTHS,decodeBootFrame,decodeApplicationFrame} from '../site/assets/tools-core.mjs';
import {SerialCapture} from '../site/assets/tools-serial.mjs';
if(!globalThis.crypto)globalThis.crypto=webcrypto;
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),json=p=>JSON.parse(readFileSync(resolve(root,p),'utf8'));
const registry=json('firmware/registry.json'),decodes=json('analysis/firmware/decode_catalog.json');let cells=0,edits=0;
for(const image of registry.images){
  const bytes=new Uint8Array(readFileSync(resolve(root,image.file))),base=baseAddress(bytes);
  assert.equal(base,image.base_address);assert.equal(await sha256(bytes),image.sha256);assert.equal(inspect(bytes).full_backup_verified,false);
  const maps=json(decodes.images.find(i=>i.id===image.id).maps_path);
  for(const m of maps){
    for(let i=0;i<m.rows*m.columns;i++){assert.equal(readCell(bytes,base,m,i),m.raw_values[Math.floor(i/m.columns)][i%m.columns]);cells++}
    const draft=bytes.slice();
    for(const index of new Set([0,m.rows*m.columns-1])){
      const before=readCell(bytes,base,m,index),after=before===0?1:0,change=editCell(draft,base,m,index,after),diff=differences(bytes,draft,base);
      assert.ok(diff.length>0&&diff.length<=m.element_bytes);assert.ok(diff.every(d=>d.address>=change.address&&d.address<change.address+m.element_bytes));
      assert.equal(readCell(bytes,base,m,index),before);assert.equal(readCell(draft,base,m,index),after);editCell(draft,base,m,index,before);assert.deepEqual(draft,bytes);edits++;
    }
    for(const bad of [-1,.5,NaN,Infinity,m.element_bytes===2?65536:256])assert.throws(()=>editCell(draft,base,m,0,bad));
    assert.throws(()=>editCell(draft,base,m,-1,0));assert.throws(()=>readCell(draft,base,m,m.rows*m.columns));assert.throws(()=>editCell(draft,base,{...m,data_address:'0xF800'},0,0));
  }
}
assert.throws(()=>baseAddress(new Uint8Array(65535)));assert.throws(()=>differences(new Uint8Array(2),new Uint8Array(3),0));
const owner=new Uint8Array(readFileSync(resolve(root,registry.images[0].file)));assert.equal(wordSum(owner,0),0xAAD5);
assert.equal(wordSum(new Uint8Array(readFileSync(resolve(root,registry.images.find(i=>i.id.endsWith('checksum-fixed')).file))),0),0xAA55);
assert.throws(()=>wordSum(owner,0,0x1801));
assert.deepEqual([...bootReadPreview(0x1800,0)],[3,0,0,7,0x18,0,0xDE]);
for(let mode=0;mode<6;mode++){const b=bootReadPreview(0x1800,mode);assert.equal(decodeBootFrame(b).length,7);b[6]^=1;assert.throws(()=>decodeBootFrame(b))}
assert.throws(()=>bootReadPreview(0xFFFE,1));assert.throws(()=>bootReadPreview(-1,0));assert.throws(()=>bootReadPreview(0,6));
assert.throws(()=>decodeBootFrame(Uint8Array.of(3,0,0,9,0,0,0)));assert.throws(()=>parseHex('0x1'));assert.throws(()=>parseHex('zz'));assert.deepEqual([...parseHex('0x03, 00:07')],[3,0,7]);
assert.equal(decodeApplicationFrame(Uint8Array.of(1,2,3,4,10)).selected_value,4);assert.throws(()=>decodeApplicationFrame(Uint8Array.of(1,2,3,4,11)));
// Compare protocol claims against source bytes, not only a round-trip of our codec.
const boot=new Uint8Array(readFileSync(resolve(root,'firmware/images/xt660-2004-2006-companion.bin'))),at=a=>a-0x1800;
const dispatch=[0xF904,0xF913,0xF945,0xF99A,0xF904,0xF9C8,0xF904,0xF9E9,0xFA35,0xFB63,0xF904,0xF904,0xF904,0xFBFE,0xFC1F,0xFD1C];
dispatch.forEach((target,i)=>assert.equal((boot[at(0xFF30+2*i)]<<8)|boot[at(0xFF31+2*i)],target));
for(const [i,address] of [0xF99A,0xF9A2,0xF9A9,0xF9B0,0xF9B7,0xF9BE].entries()){
  assert.equal(boot[at(address)],0xCE);assert.equal((boot[at(address+1)]<<8)|boot[at(address+2)],READ_LENGTHS[i]+5);
}
assert.deepEqual([...boot.slice(at(0xFDFF),at(0xFE04))],[0x96,0x23,0x40,0x5A,0xCF]);
assert.deepEqual([...boot.slice(at(0xFE7B),at(0xFE80))],[0x9B,0x23,0x97,0x26,0x0D]);
// A fake serial adapter proves bounded receive/close without touching hardware.
function mock(){let controller;const port={opened:0,closed:0,async open(options){this.options=options;this.opened++;this.readable=new ReadableStream({start(c){controller=c}})},async close(){this.closed++},get writable(){throw Error('Transmit access is forbidden')}};return {port,push:b=>controller.enqueue(Uint8Array.from(b)),end:()=>controller.close(),fail:()=>controller.error(Error('USB unplugged'))}}
const tick=()=>new Promise(r=>setTimeout(r,0));
let m=mock(),states=[],c=new SerialCapture({limit:5,onState:s=>states.push(s)});await c.connect(m.port,15625);m.push([1,2]);await tick();m.push([3,4,5,6]);await c.task;assert.equal(c.count,5);assert.equal(m.port.closed,1);assert.equal(c.report().frame_boundaries_known,false);assert.match(c.error,/limit/);assert.equal(m.port.options.flowControl,'none');assert.equal(c.port,null);
m=mock();c=new SerialCapture();await c.connect(m.port,9600);m.push([8,9]);await tick();await c.disconnect();assert.equal(c.count,2);assert.equal(m.port.closed,1);
m=mock();await c.connect(m.port,15625);assert.equal(c.count,0);m.fail();await c.task;assert.match(c.error,/USB unplugged/);assert.equal(m.port.closed,1);
await assert.rejects(()=>c.connect(mock().port,0));await assert.rejects(()=>c.connect({open:async()=>{throw Error('Port busy')}},15625));assert.equal(c.port,null);assert.equal(c.busy,false);
console.log(`Tools verified: ${registry.images.length} BIN identities, ${cells} source cells, ${edits} edit/undo boundaries; checksum fixtures, boot-byte anchors, malformed frames and receive-only serial lifecycle.`);
