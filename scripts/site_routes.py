"""Real static bike routes, retaining exact profile/BIN identity without query strings."""
import json
import posixpath
import re
from html import escape, unescape
from urllib.parse import urlsplit, urlunsplit

SECTIONS={'overview':'index.html','wiring':'wiring/index.html','research':'research/index.html',
          'pins':'pins/index.html','maps':'maps/index.html'}

def routes(data):
    models={m['id'] for m in data['models'] if not m.get('reference_only')}
    result=[]
    for p in data['profiles']:
        if p['model'] not in models:continue
        for index,i in enumerate(p['firmware_ids']):
            suffix='' if index==0 else ('checksum-corrected/' if i.endswith('checksum-fixed') else 'companion/' if i.endswith('companion') else 'immo-off/')
            result.append(dict(profile=p['id'],firmware=i,path=p['route']+suffix))
    assert len({r['path'] for r in result})==len(result)
    return result

def build(root,site,write):
    data=json.loads((root/'dataset/vehicles.json').read_text(encoding='utf-8'))
    records=routes(data)
    write('vehicles/routes.json',json.dumps(records,indent=2)+'\n')
    for record in records:
        for section,source in SECTIONS.items():
            target=record['path']+('' if section=='overview' else section+'/')+'index.html'
            markup=(site/source).read_text(encoding='utf-8')
            def adjust(match):
                key,value=match.group(1),unescape(match.group(2))
                u=urlsplit(value)
                if u.scheme or u.netloc or not u.path or u.path.startswith('/'):return match.group(0)
                path=posixpath.normpath(posixpath.join(posixpath.dirname(source),u.path))
                if u.path.endswith('/'):path+='/'
                value=urlunsplit(('', '',posixpath.relpath(path,posixpath.dirname(target))+('/' if path.endswith('/') else ''),u.query,u.fragment))
                return key+'="'+escape(value,quote=True)+'"'
            markup=re.sub(r'(href|src)="([^"]*)"',adjust,markup)
            relative_root=posixpath.relpath('.',posixpath.dirname(target))+'/'
            markup=re.sub(r'data-root="[^"]*"',f'data-root="{relative_root}" data-profile="{record["profile"]}" data-firmware="{record["firmware"]}" data-section="{section}"',markup,count=1)
            # Per-BIN grids already have stable paths; the maps alias routes there in JS.
            write(target,markup)
    return records
