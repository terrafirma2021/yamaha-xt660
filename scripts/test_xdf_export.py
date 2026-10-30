"""Parse exported XML independently and compare every address/value to the BIN."""
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
exports=json.loads(subprocess.check_output(['node','--input-type=module','-e',"""
import {readFileSync} from 'node:fs';
import {exportXdf} from './site/assets/tools-map-core.mjs';
const j=p=>JSON.parse(readFileSync(p,'utf8')),catalog=j('analysis/firmware/catalog.json'),d=j('analysis/firmware/decode_catalog.json');
console.log(JSON.stringify(catalog.images.map(i=>({id:i.id,xml:exportXdf(new Uint8Array(readFileSync(i.file)),i.base_address,j(d.images.find(x=>x.id===i.id).maps_path),i)}))));
"""],cwd=ROOT,text=True,encoding='utf-8'))
catalog=json.loads((ROOT/'analysis/firmware/catalog.json').read_text(encoding="utf-8"))
decodes=json.loads((ROOT/'analysis/firmware/decode_catalog.json').read_text(encoding="utf-8"))
cells=0;tables=0
for export in exports:
    image=next(i for i in catalog['images'] if i['id']==export['id'])
    maps=json.loads((ROOT/next(i for i in decodes['images'] if i['id']==image['id'])['maps_path']).read_text(encoding="utf-8"))
    data=(ROOT/image['file']).read_bytes();root=ET.fromstring(export['xml'])
    assert root.tag=='XDFFORMAT' and root.attrib['version']=='1.70'
    assert int(root.find('XDFHEADER/REGION').attrib['size'],16)==len(data)
    defaults=root.find('XDFHEADER/DEFAULTS');assert defaults.attrib['lsbfirst']=='0' and defaults.attrib['signed']=='0'
    entries=root.findall('XDFTABLE');assert len(entries)==len(maps)
    for table,m in zip(entries,maps):
        assert table.findtext('title')==m['display_name']
        z=table.find("XDFAXIS[@id='z']");e=z.find('EMBEDDEDDATA');offset=int(e.attrib['mmedaddress'],16)
        assert offset==int(m['data_address'],16)-image['base_address']
        assert int(e.attrib['mmedelementsizebits'])==m['element_bytes']*8
        assert int(e.attrib['mmedrowcount'])==m['rows'] and int(e.attrib['mmedcolcount'])==m['columns']
        assert z.find('MATH').attrib['equation']=='X'
        expected=[v for row in m['raw_values'] for v in row]
        for k,v in enumerate(expected):
            a=offset+k*m['element_bytes'];assert int.from_bytes(data[a:a+m['element_bytes']],'big')==v;cells+=1
        for axis,n in [('x',m['columns']),('y',m['rows'])]:
            a=table.find(f"XDFAXIS[@id='{axis}']");assert a.findtext('outputtype')=='4'
            assert len(a.findall('LABEL'))==n and int(a.findtext('indexcount'))==n
        tables+=1
print(f'XDF XML verified: {tables} tables, {cells} source cells, both BIN bases, big-endian values, labels and identity. Native TunerPro import not exercised.')
