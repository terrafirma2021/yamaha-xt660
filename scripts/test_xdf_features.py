"""Compare independently parsed XDF patches with the established byte writers."""
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'definitions/manifest.json').read_text(encoding='utf-8'))
records=[]
for item in manifest['definitions']:
    xml=ET.parse(ROOT/item['file'])
    patches=[]
    for node in xml.findall('XDFPATCH'):
        entries=[]
        for e in node.findall('XDFPATCHENTRY'):
            size=int(e.attrib['datasize'],16)
            before=list(bytes.fromhex(e.attrib['basedata']));after=list(bytes.fromhex(e.attrib['patchdata']))
            assert len(before)==len(after)==size
            entries.append(dict(address=int(e.attrib['address'],16),before=before,after=after))
        patches.append(dict(title=node.findtext('title'),entries=entries))
    assert len(patches)==item['patches']
    assert len({p['title'] for p in patches})==len(patches)
    records.append(dict(id=item['id'],patches=patches))
script='''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {featureDefinitions,setFeature} from './flasher/core/tools-features.mjs';
import {setSpeed} from './flasher/core/tools-speed.mjs';
const records=JSON.parse(readFileSync(0,'utf8')),catalog=JSON.parse(readFileSync('analysis/firmware/catalog.json','utf8'));
let count=0;
for(const r of records){
 const identity=catalog.images.find(i=>i.id===r.id),source=readFileSync(identity.file);
 for(const patch of r.patches){
  const before=new Uint8Array(source),after=new Uint8Array(source);
  for(const e of patch.entries){before.set(e.before,e.address);after.set(e.after,e.address);}
  const expected=before.slice();
  if(patch.title==='Speedo disable')setSpeed(expected,identity,false,0);
  else if(patch.title.startsWith('Pulse offset '))setSpeed(expected,identity,true,Number(patch.title.slice(13)));
  else{
   const f=featureDefinitions(identity).find(f=>(f.id==='co-range'?f.name:'Disable '+f.name)===patch.title);
   assert(f&&f.bytes);setFeature(expected,identity,f.id,f.id==='co-range');
  }
  assert.deepEqual(after,expected,identity.id+'/'+patch.title);
  count++;
 }
}
console.log(`Verified ${count} XDF patches against reviewed byte writers; all file offsets and complete byte changes match.`);
'''
subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,input=json.dumps(records),text=True,check=True)
