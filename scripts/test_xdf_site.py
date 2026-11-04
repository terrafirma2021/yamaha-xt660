"""Definition downloads work without scripts; retired editing code is absent."""
import hashlib
import json
import posixpath
from pathlib import Path
from bs4 import BeautifulSoup
from site_routes import routes

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT/'_site'
manifest = json.loads((ROOT/'definitions/manifest.json').read_text(encoding='utf-8'))
assert manifest == json.loads((SITE/'xdf/manifest.json').read_text(encoding='utf-8'))
for record in manifest['definitions']:
    data = (SITE/'xdf/files'/Path(record['file']).name).read_bytes()
    assert data == (ROOT/record['file']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == record['xdf_sha256']
    assert hashlib.sha256((SITE/'firmware/bins'/(record['id']+'.bin')).read_bytes()).hexdigest() == record['bin_sha256']
for record in routes(json.loads((ROOT/'dataset/vehicles.json').read_text(encoding='utf-8'))):
    page = record['path']+'xdf/index.html'
    soup = BeautifulSoup((SITE/page).read_text(encoding='utf-8'),'html.parser')
    chosen = soup.select_one('#xdf-selected .xdf-download[download]')
    target = posixpath.normpath(posixpath.join(posixpath.dirname(page),chosen['href']))
    assert target == 'xdf/files/'+record['firmware']+'.xdf'
    assert (SITE/target).is_file()
    assert len(soup.select('.downloads-table a[download][href$=".xdf"]')) == len(manifest['definitions'])
    assert soup.select_one('nav[aria-label="Main navigation"] a[aria-current="page"]').get_text() == 'Downloads'
for file in ('tools.mjs','tools-workspace.mjs','tools-map-core.mjs','tools.css','tools-redirect.js','vehicles.js','flashing.mjs'):
    assert not (ROOT/'site/assets'/file).exists()
    assert not (SITE/'assets'/file).exists()
assert not (ROOT/'analysis/firmware/MAP_WORKSPACE.md').exists()
for path in SITE.rglob('*.html'):
    text = path.read_text(encoding='utf-8')
    for marker in ('id="map-workspace"','id="feature-list"','id="tune-grid"','id="map-apply"','id="edit-undo"'):
        assert marker not in text, (path, marker)
print(f'XDF website checked: {len(manifest["definitions"])} exact downloads, model/BIN links, and no browser tuning editor or retired assets.')
