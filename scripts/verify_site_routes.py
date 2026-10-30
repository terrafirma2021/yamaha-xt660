"""Verify clean static URLs and availability without inventing catalogue/BIN matches."""
import json
import re
import subprocess
from pathlib import Path
from site_routes import routes, SECTIONS
ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'_site'
data=json.loads((ROOT/'dataset/vehicles.json').read_text(encoding='utf-8'))
registry=json.loads((ROOT/'firmware/registry.json').read_text(encoding='utf-8'))
records=routes(data)
pin_scripts=[]
assert records==json.loads((SITE/'vehicles/routes.json').read_text())
assert {r['firmware'] for r in records}=={i['id'] for i in registry['images']}
assert all('?' not in r['path'] and 'tdm' not in r['path'] for r in records)
for r in records:
    p=next(p for p in data['profiles'] if p['id']==r['profile'])
    assert r['firmware'] in p['firmware_ids']
    for section in SECTIONS:
        path=SITE/r['path']/('' if section=='overview' else section)/'index.html'
        text=path.read_text(encoding='utf-8')
        assert f'data-profile="{r["profile"]}"' in text
        assert f'data-firmware="{r["firmware"]}"' in text
        assert f'data-section="{section}"' in text
        if section=='pins':
            # URL rewriting must not corrupt template-literal JavaScript and
            # leave matched-bike pin pages stuck on the loading message.
            pin_scripts.extend(dict(name=str(path.relative_to(SITE)), code=code)
                               for attrs,code in re.findall(r'<script([^>]*)>(.*?)</script>',text,re.S)
                               if 'src=' not in attrs and 'application/json' not in attrs and code.strip())
subprocess.run(['node','-e', 'const vm=require("node:vm");let s="";process.stdin.on("data",c=>s+=c);process.stdin.on("end",()=>{for(const x of JSON.parse(s))new vm.Script(x.code,{filename:x.name});});'],
               input=json.dumps(pin_scripts),text=True,check=True)
home=(SITE/'index.html').read_text(encoding='utf-8')
pin_review=(SITE/'docs/semantics/PIN_CONFIGURATION_REVIEW.html').read_text(encoding='utf-8')
assert '<section data-study=' not in pin_review, 'Both-family findings must not be hidden for later profiles'
assert 'data-bike="tdm900"' not in home and 'TDM900 COMPARISON' not in home
assert '<div aria-disabled="true" class="bike-card xt660z"' in home
assert home.count('data-bike=')==3
for i in registry['images']:
    assert ' · ' not in i['label'] and i['variant']
    assert (SITE/'firmware'/i['id']/'index.html').exists()
print(f'Verified {len(records)} exact profile/BIN routes, {len(records)*len(SECTIONS)} static pages, all nine BINs and XT-only navigation.')
