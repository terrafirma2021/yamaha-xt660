import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve,dirname} from 'node:path';
import {webcrypto} from 'node:crypto';
import {sha256,baseAddress,inspect,wordSum,differences,readCell,editCell,parseHex,bootReadPreview,READ_LENGTHS,decodeBootFrame,decodeApplicationFrame,verifyStartupChecksum,correctStartupChecksum} from '../site/assets/tools-core.mjs';
import {SerialCapture} from '../site/assets/tools-serial.mjs';
import {XT_BOOT_PROFILE,xtReadPlan,BootReadTransaction,XtReadAssembly} from '../site/assets/tools-boot.mjs';
import {featureStates,setFeature,matchesFeatureVariant} from '../site/assets/tools-features.mjs';
if(!globalThis.crypto)globalThis.crypto=webcrypto;
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),json=p=>JSON.parse(readFileSync(resolve(root,p),'utf8'));
const registry=json('firmware/registry.json'),decodes=json('analysis/firmware/decode_catalog.json');let cells=0,edits=0;
const catalogue=json('analysis/firmware/catalog.json');
for(const image of registry.images){
  const bytes=new Uint8Array(readFileSync(resolve(root,image.file))),base=baseAddress(bytes);
  const identity=catalogue.images.find(i=>i.id===image.id),original=bytes.slice(),corrected=bytes.slice();
  const states=featureStates(bytes,identity);
  assert.deepEqual(states.map(f=>f.id),['pair','immo','overrun','o2','spark-overrun']);
  assert.equal(states[0].state,'enabled');assert.equal(states[2].state,'enabled');
  assert.equal(states[1].state,bytes[(identity.code_family==='early'?0x4E7D:0x4619)-base]===128?'disabled':'enabled');
  assert.ok(states.slice(3).every(f=>!f.editable&&f.state==='unverified'));
  const featured=bytes.slice();
  for(const id of ['pair','immo','overrun']){
    const saved=featured.slice(),change=setFeature(featured,identity,id,false);
    assert.equal(featureStates(featured,identity).find(f=>f.id===id).state,'disabled');
    assert.deepEqual(differences(saved,featured,base).map(d=>d.address),change.changes.map(d=>d.address).sort((a,b)=>a-b));
    correctStartupChecksum(featured,identity);
    assert.equal(verifyStartupChecksum(featured,identity).status,'pass');
    assert.ok(matchesFeatureVariant(featured,original,identity));
    assert.deepEqual(featured.slice(0xF800-base),original.slice(0xF800-base));
  }
  const beforeUnsupported=featured.slice();
  for(const id of ['o2','spark-overrun','missing'])assert.throws(()=>setFeature(featured,identity,id,false));
  assert.throws(()=>setFeature(featured,null,'immo',false));
  assert.deepEqual(featured,beforeUnsupported);
  const corrupt=featured.slice();corrupt[0x6000-base]^=1;
  assert.equal(matchesFeatureVariant(corrupt,original,identity),false);
  assert.equal(matchesFeatureVariant(featured,original,null),false);
  const mixed=original.slice(),pair=states[0];mixed[pair.bytes[0].address-base]=0x4D;
  assert.equal(featureStates(mixed,identity)[0].state,'unverified');
  assert.equal(matchesFeatureVariant(mixed,original,identity),false);
  assert.throws(()=>setFeature(mixed,identity,'pair',false));
  const badOperand=original.slice();badOperand[pair.bytes[0].address+2-base]^=1;
  assert.throws(()=>setFeature(badOperand,identity,'pair',false));
  for(const f of states.filter(f=>f.editable))setFeature(featured,identity,f.id,f.state==='enabled');
  correctStartupChecksum(featured,identity);
  const baseline=original.slice();correctStartupChecksum(baseline,identity);
  assert.deepEqual(featured,baseline);assert.deepEqual(bytes,original);
  assert.equal(verifyStartupChecksum(bytes,identity).status,identity.startup_checksum==='AA55'?'pass':'fail');
  assert.ok([0xFFFF,0xFF7F].includes((bytes[0xF7FC-base]<<8)|bytes[0xF7FD-base]));
  correctStartupChecksum(corrected,identity);assert.equal(wordSum(corrected,base),0xAA55);
  assert.ok(differences(bytes,corrected,base).every(d=>d.address===0xF7FC||d.address===0xF7FD));
  const stable=corrected.slice();correctStartupChecksum(corrected,identity);assert.deepEqual(corrected,stable);
  assert.equal(verifyStartupChecksum(bytes,null).status,'unverified');assert.throws(()=>correctStartupChecksum(bytes,null));assert.deepEqual(bytes,original);
  const broken=bytes.slice();broken[(identity.code_family==='early'?0xA497:0x972B)-base]^=1;const brokenBefore=broken.slice();assert.throws(()=>correctStartupChecksum(broken,identity));assert.deepEqual(broken,brokenBefore);
  const serial=identity.code_family==='early'?0x506E:0x4863;
  assert.deepEqual([...bytes.slice(serial-base,serial-base+5)],[0xCC,0,0x40,0x5C,0xD0]);
  const poll=identity.code_family==='early'?0x53C8:0x4C06;
  assert.deepEqual([...bytes.slice(poll-base,poll-base+3)],[0x16,0xF8,0xA0]);
  if(identity.boot_status==='populated'){
    assert.deepEqual([...bytes.slice(0xF86E-base,0xF873-base)],[0xCC,0,0x68,0x5C,0xC8]);
    assert.deepEqual([...bytes.slice(0xF93B-base,0xF93E-base)],[0x87,0x5A,0xD3]);
  }
  assert.equal(base,image.base_address);assert.equal(await sha256(bytes),image.sha256);assert.equal(inspect(bytes).full_backup_verified,false);
  const maps=json(decodes.images.find(i=>i.id===image.id).maps_path);
  for(const m of maps){
    for(let i=0;i<m.rows*m.columns;i++){assert.equal(readCell(bytes,base,m,i),m.raw_values[Math.floor(i/m.columns)][i%m.columns]);cells++}
    const draft=bytes.slice();
    for(const index of new Set([0,m.rows*m.columns-1])){
      const before=readCell(bytes,base,m,index),after=before===0?1:0,change=editCell(draft,base,m,index,after),diff=differences(bytes,draft,base);
      assert.ok(diff.length>0&&diff.length<=m.element_bytes);assert.ok(diff.every(d=>d.address>=change.address&&d.address<change.address+m.element_bytes));
      assert.equal(readCell(bytes,base,m,index),before);assert.equal(readCell(draft,base,m,index),after);editCell(draft,base,m,index,before);assert.deepEqual(draft,bytes);edits++;
      const checked=stable.slice();editCell(checked,base,m,index,after);correctStartupChecksum(checked,identity);
      assert.equal(wordSum(checked,base),0xAA55);assert.equal(readCell(checked,base,m,index),after);
      assert.ok(differences(bytes,checked,base).every(d=>(d.address>=change.address&&d.address<change.address+m.element_bytes)||d.address===0xF7FC||d.address===0xF7FD));
      editCell(checked,base,m,index,before);correctStartupChecksum(checked,identity);assert.deepEqual(checked,stable);assert.deepEqual(bytes,original);
    }
    for(const bad of [-1,.5,NaN,Infinity,m.element_bytes===2?65536:256])assert.throws(()=>editCell(draft,base,m,0,bad));
    assert.throws(()=>editCell(draft,base,m,-1,0));assert.throws(()=>readCell(draft,base,m,m.rows*m.columns));assert.throws(()=>editCell(draft,base,{...m,data_address:'0xF800'},0,0));
  }
}
// Review compensation padding against decoded instruction boundaries and static targets.
for(const stem of ['analysis','analysis/firmware/families/late']){
  for(const line of readFileSync(resolve(root,stem,'disassembly.tsv'),'utf8').trim().split(/\r?\n/).slice(1)){
    const [address,code]=line.split('\t'),a=parseInt(address,16);assert.ok(a>=0xF7FE||a+code.length/2<=0xF7FC);
  }
  for(const line of readFileSync(resolve(root,stem,'references.tsv'),'utf8').trim().split(/\r?\n/).slice(1))assert.ok(![0xF7FC,0xF7FD].includes(parseInt(line.split('\t')[1],16)));
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
// YamahaFlasher's XT path: 116 addressed 512-byte reads, 7 echoed bytes + 517-byte reply.
assert.equal(XT_BOOT_PROFILE.baudRate,9600);assert.equal(XT_BOOT_PROFILE.hardwareValidated,false);
const plan=xtReadPlan();assert.equal(plan.length,116);assert.equal(plan.at(-1).address,0xFE00);
assert.deepEqual([...plan[0].request],[3,2,0,7,0x18,0,0xDC]);
function readFixture(address,echo=true){
  const reply=new Uint8Array(517);reply.set([3,0,2,5]);reply.set(boot.subarray(address-0x1800,address-0x1800+512),4);
  let sum=0;for(let i=0;i<516;i++)sum+=reply[i];reply[516]=(-sum)&255;
  return echo?Uint8Array.from([...bootReadPreview(address,2),...reply]):reply;
}
const wire=readFixture(0x1800);
for(let split=0;split<wire.length;split++){
  const tx=new BootReadTransaction(0x1800);tx.feed(wire.slice(0,split));tx.feed(wire.slice(split));
  assert.deepEqual(tx.finish(),boot.slice(0,512));
}
const bytewise=new BootReadTransaction(0x1800);for(const byte of wire)bytewise.feed(Uint8Array.of(byte));
assert.deepEqual(bytewise.finish(),boot.slice(0,512));
const direct=new BootReadTransaction(0x1800,{echo:false});direct.feed(readFixture(0x1800,false));assert.ok(direct.complete);
for(const index of [0,7,8,9,10,100,523]){
  const corrupt=wire.slice();corrupt[index]^=1;const tx=new BootReadTransaction(0x1800);
  assert.throws(()=>tx.feed(corrupt));assert.throws(()=>tx.finish());assert.throws(()=>tx.feed(wire));
}
const short=new BootReadTransaction(0x1800);short.feed(wire.slice(0,-1));assert.throws(()=>short.finish());
assert.throws(()=>new BootReadTransaction(0x1800).feed(Uint8Array.from([...wire,0])));
assert.throws(()=>new BootReadTransaction(0x1800).feed(readFixture(0x1800,false)));
for(const address of [0,0x1801,0xFFFF,0x10000,NaN])assert.throws(()=>new BootReadTransaction(address));
assert.throws(()=>new BootReadTransaction(0x1800,{echo:'auto'}));
const assembly=new XtReadAssembly();assert.throws(()=>assembly.finish());assert.throws(()=>assembly.add(short));
for(const item of plan.toReversed()){
  const tx=new BootReadTransaction(item.address);tx.feed(readFixture(item.address));assembly.add(tx);
  assert.throws(()=>assembly.add(tx));
}
assert.equal(assembly.blocksReceived,116);assert.deepEqual(assembly.finish(),boot);
const isolated=assembly.finish();isolated.fill(0);assert.deepEqual(assembly.finish(),boot);
// A fake serial adapter proves bounded receive/close without touching hardware.
function mock(){let controller;const port={opened:0,closed:0,async open(options){this.options=options;this.opened++;this.readable=new ReadableStream({start(c){controller=c}})},async close(){this.closed++},get writable(){throw Error('Transmit access is forbidden')}};return {port,push:b=>controller.enqueue(Uint8Array.from(b)),end:()=>controller.close(),fail:()=>controller.error(Error('USB unplugged'))}}
const tick=()=>new Promise(r=>setTimeout(r,0));
let m=mock(),states=[],c=new SerialCapture({limit:5,onState:s=>states.push(s)});await c.connect(m.port,15625);m.push([1,2]);await tick();m.push([3,4,5,6]);await c.task;assert.equal(c.count,5);assert.equal(m.port.closed,1);assert.equal(c.report().frame_boundaries_known,false);assert.match(c.error,/limit/);assert.equal(m.port.options.flowControl,'none');assert.equal(c.port,null);
m=mock();c=new SerialCapture();await c.connect(m.port,9600);m.push([8,9]);await tick();await c.disconnect();assert.equal(c.count,2);assert.equal(m.port.closed,1);
m=mock();await c.connect(m.port,15625);assert.equal(c.count,0);m.fail();await c.task;assert.match(c.error,/USB unplugged/);assert.equal(m.port.closed,1);
await assert.rejects(()=>c.connect(mock().port,0));await assert.rejects(()=>c.connect({open:async()=>{throw Error('Port busy')}},15625));assert.equal(c.port,null);assert.equal(c.busy,false);
console.log(`Tools verified: ${registry.images.length} BIN identities, ${cells} source cells, ${edits} edit/undo/checksum boundaries; 116-block XT assembly, 524 chunk splits, echo/reply validation, compensation bounds, both UART profiles, boot-byte anchors and receive-only serial lifecycle.`);
