// Exercise the released WASM runtime through its external ADC and dash controls.
// No RAM edits, handler replacement, or assumed conversion from bytes to volts.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const bundle=resolve(process.argv[2]??`${root}/emulator/browser/runtime`);
const output=resolve(process.argv[3]??`${root}/emulator/.runs/supply-diagnostics.json`);
const hash=path=>createHash('sha256').update(readFileSync(path)).digest('hex');
const create=(await import(pathToFileURL(`${bundle}/xt660.mjs`))).default;
const core=await create({locateFile:name=>`${bundle}/${name}`,print:()=>{},printErr:console.error});
function call(name,data) {
  const value=JSON.parse(core.ccall(name,'string',data===undefined?[]:['string'],data===undefined?[]:[JSON.stringify(data)]));
  assert(!value?.error,value?.error);return value;
}
const action=data=>call('xt_action',data);
const state=()=>call('xt_state');
const ticks=n=>{for(let i=0;i<n;i++)call('xt_tick');return state();};
const images=call('xt_init').images;
assert.equal(images.length,5);
const samples=[0,3,4,148,151,152,153,448,451,452,511,512,515,516,615,616,736,952,956,960,1023];
const results=[];
for(const image of images) {
  action({action:'load',image:image.id});
  action({action:'diagnostics',enabled:true});
  let s=state(),entry=0;
  while(s.bike.meter.mode!=='diagnostic'&&entry++<240)s=ticks(1);
  assert.equal(s.bike.meter.mode,'diagnostic');
  for(let n=0;s.bike.meter.diagnostic_id!==9&&n<30;n++)
    s=action({action:'diagnostic-next',direction:1});
  assert.equal(s.bike.meter.diagnostic_id,9);
  s=ticks(3);assert.equal(s.bike.meter.diagnostic_value,0,'Run-off fixture must remove supply');
  action({action:'control',name:'run',value:true});
  s=ticks(3);assert.equal(s.bike.meter.diagnostic_value,136,'Existing midpoint fixture');
  const rows=[];
  for(const adc of samples) {
    action({action:'adc',channel:4,value:adc});s=ticks(3);
    const m=s.bike.meter,expected=Math.min(254,Math.floor((adc>>2)*256/240));
    assert.equal(m.diagnostic_id,9);
    assert.equal(m.diagnostic_value,expected,`${image.id}: ADC4 ${adc}`);
    assert.equal(m.frame.length,5);
    assert.equal(m.frame.slice(0,4).reduce((a,b)=>a+b,0)&255,m.frame[4]);
    rows.push({adc10:adc,adc_high:adc>>2,diagnostic_reply:m.diagnostic_value,frame:m.frame});
  }
  action({action:'control',name:'run',value:false});
  s=ticks(3);assert.equal(s.bike.meter.diagnostic_value,0);
  action({action:'verify'});
  // Check fault 46 under normal execution, where diagnostic mode no longer
  // suppresses qualification. Use the same channel and untouched firmware.
  action({action:'diagnostics',enabled:false});
  action({action:'start'});s=state();
  for(let n=0;!s.bike.rotating&&n<100;n++)s=ticks(1);
  assert(s.bike.rotating,'Engine must start before the supply-fault checks');
  s=ticks(20);assert.equal(s.faults[2]&1,0);
  const faultRows=[];
  for(const [adc,fault46] of [[508,true],[512,false],[452,true],[616,false],[796,false],[800,true],[736,false]]) {
    action({action:'adc',channel:4,value:adc});s=ticks(20);
    for(let n=0;Boolean(s.faults[2]&1)!==fault46&&n<160;n++)s=ticks(1);
    assert.equal(Boolean(s.faults[2]&1),fault46,`${image.id}: fault 46 at ADC4 ${adc}`);
    faultRows.push({adc10:adc,adc_high:adc>>2,fault46:Boolean(s.faults[2]&1),fault_bytes:s.faults});
  }
  action({action:'verify'});
  results.push({image:image.id,diagnostic:9,run_off_reply:0,default_run_on_reply:136,
    rows,normal_fault46:faultRows,source_flash_unchanged:true});
  console.log(`${image.id}: ${rows.length} ADC/reply cases, ${faultRows.length} fault-46 cases; run on/off and BIN integrity passed.`);
}
mkdirSync(dirname(output),{recursive:true});
writeFileSync(output,JSON.stringify({scope:'Full firmware ADC sampling and d:09 replies in released WASM; external inputs only. Volts conversion is not established.',
  artifacts:Object.fromEntries(['xt660.wasm','xt660.mjs','xt660.data'].map(n=>[n,hash(`${bundle}/${n}`)])),
  test_sha256:hash(fileURLToPath(import.meta.url)),adc_channel:4,
  expected:'min(254, floor((adc10 >> 2) * 256 / 240))',
  cases:results.reduce((sum,x)=>sum+x.rows.length,0),
  fault46_cases:results.reduce((sum,x)=>sum+x.normal_fault46.length,0),images:results},null,2)+'\n');
console.log(output);
