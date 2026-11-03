"""Reading/navigation must be complete in downloaded HTML, with no JS execution."""
import json
import posixpath
from pathlib import Path
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from site_routes import routes, SECTIONS
from site_static import FORMAT

# Rendering must preserve code examples as text, including literal tag-like values.
example=BeautifulSoup('<pre>&lt;register&gt; &amp; value</pre>','html.parser')
roundtrip=BeautifulSoup(example.decode(formatter=FORMAT),'html.parser')
assert roundtrip.pre.get_text()=='<register> & value' and roundtrip.pre.find() is None

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'_site'
data=json.loads((SITE/'vehicles/catalog.json').read_text())
images={i['id']:i for i in json.loads((SITE/'firmware/catalog.json').read_text())['images']}
audit=json.loads((SITE/'pins/pin_audit.json').read_text())
parse=lambda path: BeautifulSoup((SITE/path).read_text(encoding='utf-8'),'html.parser')
records=routes(data)
for record in records:
    image=images[record['firmware']]
    reviewed=next(i for i in audit['images'] if i['id']==image['id'])
    family=audit['families'][reviewed['family']]
    for section in SECTIONS:
        path=record['path']+('' if section=='overview' else section+'/')+'index.html'
        soup=parse(path)
        panel=soup.find(id='vehicle-context')
        assert panel['data-firmware']==image['id']
        assert len(panel.select('.static-picker a'))==len(records)
        assert soup.find(id='theme-light') and soup.find(id='theme-dark')
        for a in soup.select('nav[aria-label="Main navigation"] a'):
            href=a['href']
            if a.get_text() in ('Overview','Maps','Wiring','MCU pins','Flashing','Tune','Research'):
                destination=posixpath.normpath(posixpath.join(posixpath.dirname(path),href))+'/'
                assert destination.startswith(record['path']),(path,href)
        if section in ('overview','wiring','research'):
            node=soup.find(id={'overview':'vehicle-overview','wiring':'vehicle-hardware','research':'vehicle-research'}[section])
            assert image['label'] in node.get_text() and node.find('img')
        if section=='pins':
            assert soup.find(id='pin-scope')['data-firmware']==image['id']
            assert len(soup.select('[data-static-pin]'))==80
            assert len(soup.select('.connector-scroll .connector-slot'))==len(family['connector']['slots'])
            embedded=json.loads(soup.find(id='pin-data').string)
            for p in embedded['pins']:
                assert p['check']==next(c for c in reviewed['checks'] if c['pin']==p['pin'])
                assert p['role'] in soup.find(id='pin-'+str(p['pin'])).get_text()
            assert soup.find(id='family-notes').get_text().startswith('Early' if image['code_family']=='early' else 'Later')
        if section=='flashing':
            node=soup.find(id='connection-content')
            assert 'hidden' not in node.attrs
            assert len(node.select('.flash-slot'))==len(family['connector']['slots'])
            assert [(g['data-position'],g['data-signal']) for g in node.select('[data-signal]')]==[('U03','power'),('U07','ground'),('U12','kline')]
            assert node.select_one('#kkl-diagram svg')
        if section=='maps':
            assert len(soup.select('.map-card'))==image['decoded_map_count']
            if not image.get('shared_map_count'):
                assert image['label'] in soup.h1.parent.get_text()
        if section=='tune':
            assert soup.select_one('.tools-fallback a[download]')
            assert 'JavaScript' in soup.select_one('.tools-fallback').get_text()
home=parse('index.html')
assert home.select_one('#vehicle-overview .vehicle-summary')
assert len(home.select('.static-picker a'))==len(records)
legacy=parse('tools/index.html')
assert {'Flashing & backup','Tune features & maps'} <= {a.get_text() for a in legacy.select('main a')}
for page in SITE.rglob('*.html'):
    text=page.read_text(encoding='utf-8')
    assert 'scope-pending' not in text,page
    soup=BeautifulSoup(text,'html.parser')
    assert all(not urlsplit(s['src']).netloc for s in soup.select('script[src]'))
    assert soup.select_one('#selection-status').get_text().strip()
print(f'No-script HTML checks passed: {len(records)} selections, both connectors, 80 pins per page, correct per-BIN maps, plain navigation and CSS themes.')
