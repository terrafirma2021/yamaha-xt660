// Deterministic, ready-to-use definitions from the reviewed per-BIN catalogues.
import {readFileSync,writeFileSync,mkdirSync,readdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {featurePatches} from './lib/xdf-features.mjs';
import {exportXdf} from './lib/xdf.mjs';
const root=new URL('../',import.meta.url),json=p=>JSON.parse(readFileSync(new URL(p,root),'utf8'));
const hash=data=>createHash('sha256').update(data).digest('hex');
const check=process.argv.includes('--check');
const images=json('analysis/firmware/catalog.json').images,decodes=json('analysis/firmware/decode_catalog.json').images;
const expected=new Set(),records=[];
function emit(path,text){
  expected.add(path.split('/').at(-1));
  const file=new URL(path,root);
  if(check){if(readFileSync(file,'utf8')!==text)throw Error('Stale XDF output: '+path+'; run node scripts/build_xdfs.mjs');}
  else writeFileSync(file,text);
}
if(!check)mkdirSync(new URL('definitions/',root),{recursive:true});
for(const identity of images){
  const bytes=readFileSync(new URL(identity.file,root));
  if(hash(bytes)!==identity.sha256||bytes.length!==identity.size)throw Error('Source BIN identity mismatch: '+identity.id);
  const decoded=decodes.find(d=>d.id===identity.id);
  if(!decoded)throw Error('Missing map catalogue: '+identity.id);
  const maps=json(decoded.maps_path),text=exportXdf(bytes,identity.base_address,maps,identity);
  const path='definitions/'+identity.id+'.xdf';
  emit(path,text);
  records.push({id:identity.id,label:identity.label,variant:identity.variant,file:path,bin_file:identity.file,
    bin_size:bytes.length,base_address:identity.base_address,bin_sha256:identity.sha256,
    xdf_sha256:hash(text),patches:featurePatches(bytes,identity).length,maps:maps.length,cells:maps.reduce((n,m)=>n+m.rows*m.columns,0)});
}
emit('definitions/manifest.json',JSON.stringify({schema_version:1,format:'XDF 1.70',definitions:records},null,2)+'\n');
// Do not silently leave definitions for a removed or renamed BIN in the library.
for(const name of readdirSync(new URL('definitions/',root)))if(name.endsWith('.xdf')&&!expected.has(name))throw Error('Unregistered XDF: '+name);
console.log(`${check?'Verified':'Generated'} ${records.length} XDFs, ${records.reduce((n,r)=>n+r.maps,0)} map definitions; source BIN hashes and file bases checked.`);
