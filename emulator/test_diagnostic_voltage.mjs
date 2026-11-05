// Check the actual dash formatter against firmware-captured d:09 replies.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname,resolve} from 'node:path';
import vm from 'node:vm';

const root=dirname(fileURLToPath(import.meta.url));
const source=readFileSync(resolve(root,'web/dashboard.js'),'utf8');
const start=source.indexOf('function diagnosticReading(');
assert(start>=0);
const formatter=vm.runInNewContext('('+source.slice(start,source.indexOf('\nfunction lock(',start)).trim()+')');
const display=(raw,id=9,mode='diagnostic')=>formatter({mode,diagnostic_id:id,diagnostic_value:raw});
const report=JSON.parse(readFileSync(resolve(root,'supply-diagnostics-validation.json'),'utf8'));
let captured=0;
for(const image of report.images)for(const row of image.rows){
  const got=display(row.diagnostic_reply);
  assert.equal(got.unit,'V · EST.');
  if(row.diagnostic_reply===254)assert.equal(got.value,'≥18.7');
  else assert.equal(got.value,((row.adc10>>2)*20/256).toFixed(1),`${image.image}: ADC ${row.adc10}`);
  captured++;
}
// Every unsaturated source code must round-trip, including the skipped wire
// values created by integer division. A plain multiplier fails these cases.
const reachable=new Set();
for(let high=0;high<=255;high++){
  const raw=Math.min(254,Math.floor(high*256/240));reachable.add(raw);
  assert.equal(display(raw).value,raw===254?'≥18.7':(high*20/256).toFixed(1));
}
for(let raw=0;raw<=255;raw++)if(!reachable.has(raw))assert.equal(display(raw).value,'—');
for(const raw of [null,undefined,NaN,-1,256,1.5,'163'])assert.equal(display(raw).value,'—');
assert.equal(display(163).value,'12.0');assert.equal(display(196).value,'14.4');
assert.equal(display(0).value,'0.0');
for(const id of [1,3,5,6,7,8,20,21,30,61,62]){
  assert.equal(display(163,id).value,'163');assert.equal(display(163,id).unit,'ECU REPLY');
}
assert.equal(display(163,9,'hold-menu').value,'—');
assert.equal(display(163,9,'normal').unit,'ECU REPLY');
console.log(`${captured} captured replies, all 256 ADC high bytes, invalid/missing/saturated codes and other diagnostic items passed.`);
