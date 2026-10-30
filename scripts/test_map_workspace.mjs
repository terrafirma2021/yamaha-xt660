import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {rectangle,indices,parseCells,previewEdit,exportXdf,matchesMapVariant} from '../site/assets/tools-map-core.mjs';
import {baseAddress,readCell} from '../site/assets/tools-core.mjs';
const m={rows:3,columns:3,element_bytes:1,column_axis:{raw_values:[0,1,4]},row_axis:{raw_values:[0,2,4]}};
const a=[0,99,40,20,90,60,40,80,80],s=rectangle(m,0,8);
assert.deepEqual(indices(m,rectangle(m,8,4)),[4,5,7,8]);
assert.throws(()=>rectangle(m,-1,8));
assert.deepEqual(previewEdit(m,a,a,s,'horizontal',0).map(p=>[p.index,p.after]),[[1,10],[4,30],[7,50]]);
assert.deepEqual(previewEdit(m,a,a,s,'vertical',0),[]);
assert.deepEqual(parseCells('1\t2\n3\t4'),[[1,2],[3,4]]);
assert.throws(()=>parseCells('1 2\n3'));assert.throws(()=>parseCells('1e3'));
assert.throws(()=>previewEdit(m,a,a,s,'add',200));
assert.throws(()=>previewEdit(m,a,a,s,'set',1.5));
assert.throws(()=>previewEdit(m,a,a,s,'multiply',Infinity));
assert.throws(()=>previewEdit(m,a,a,rectangle(m,8,8),'paste',0,'1 2'));
assert.deepEqual(previewEdit(m,a,a,rectangle(m,4,4),'paste',0,'1 2\n3 4').map(p=>p.index),[4,5,7,8]);
assert.equal(previewEdit(m,a,a,s,'smooth',0).find(p=>p.index===4).after,Math.round(a.reduce((x,y)=>x+y)/9));
assert.equal(previewEdit(m,a,a,rectangle(m,0,0),'multiply',1.1).length,0);
const json=p=>JSON.parse(readFileSync(new URL('../'+p,import.meta.url),'utf8'));
const registry=json('analysis/firmware/catalog.json'),decodes=json('analysis/firmware/decode_catalog.json');let count=0;
for(const image of registry.images){
 const b=new Uint8Array(readFileSync(new URL('../'+image.file,import.meta.url))),maps=json(decodes.images.find(i=>i.id===image.id).maps_path),base=baseAddress(b);
 for(const map of maps){
  const v=Array.from({length:map.rows*map.columns},(_,i)=>readCell(b,base,map,i)),r=rectangle(map,0,v.length-1);
  assert.deepEqual(previewEdit(map,v,v,r,'multiply',1),[]);
  assert.deepEqual(previewEdit(map,v,v,r,'restore',0),[]);
  const edit=previewEdit(map,v,v,r,'set',0);assert.ok(edit.every(p=>p.after===0&&p.before===v[p.index]));count+=v.length;
 }
 const edited=b.slice();edited[Number(maps[0].data_address)-base]^=1;assert.ok(matchesMapVariant(edited,b,image,maps));edited[0xF700-base]^=1;assert.ok(!matchesMapVariant(edited,b,image,maps));
 const xdf=exportXdf(b,base,maps,image);assert.equal((xdf.match(/<XDFTABLE /g)||[]).length,maps.length);assert.ok(xdf.includes('BASEOFFSET offset="0"'));
}
console.log(`Map workspace operations passed; ${count} cells across nine BINs, selection, axis-weighted interpolation, paste, smoothing and range rejection.`);
