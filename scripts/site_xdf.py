"""Publish generated XDF downloads; no browser calibration editor."""
import json
import subprocess
from html import escape as esc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def selected_definition(image, url):
    return f'''<h2>{esc(image['label'])}</h2>
<p>{esc(image['variant'])} · {image['size']:,} bytes · {image['decoded_map_count']} maps</p>
<div class="xdf-actions"><a class="xdf-download" href="{url('xdf/files/'+image['id']+'.xdf')}" download>Download XDF</a>
<a href="{url('firmware/bins/'+image['id']+'.bin')}" download>Matching BIN</a>
<a href="{url('firmware/'+image['id']+'/')}">Firmware details ↗</a></div>'''


def build(shell, write, catalog):
    subprocess.run(['node', str(ROOT/'scripts/build_xdfs.mjs'), '--check'], cwd=ROOT, check=True)
    manifest = json.loads((ROOT/'definitions/manifest.json').read_text(encoding='utf-8'))
    decode = json.loads((ROOT/'analysis/firmware/decode_catalog.json').read_text(encoding='utf-8'))
    for image in catalog['images']:
        write('firmware/bins/'+image['id']+'.bin', (ROOT/image['file']).read_bytes())
        row = next(r for r in decode['images'] if r['id']==image['id'])
        maps = json.loads((ROOT/row['maps_path']).read_text(encoding='utf-8'))
        # Layouts support read-only identity matching on the flashing page.
        keys = ('id','data_address','end_exclusive','rows','columns','element_bytes','byte_order')
        write('firmware/layouts/'+image['id']+'.json', json.dumps([{k:m[k] for k in keys if k in m} for m in maps])+'\n')
    cards = []
    for item in manifest['definitions']:
        write('xdf/files/'+item['id']+'.xdf', (ROOT/item['file']).read_bytes())
        cards.append(f'''<tr data-xdf="{item['id']}"><td><a href="../firmware/{item['id']}/">{esc(item['label'])}</a><small>{esc(item['variant'])}</small></td>
<td class="file-size">{item['bin_size']:,}</td><td>{item['maps']}</td>
<td><a href="../firmware/bins/{item['id']}.bin" download>BIN</a></td><td><a href="files/{item['id']}.xdf" download>XDF</a></td></tr>''')
    body = '''<div class="page-heading"><h1>Downloads</h1></div>
<section class="download-bundle"><div><h2>Complete Windows bundle</h2><p>9 BINs · 9 XDFs · XT660 Flash Tool</p><p>Read · Write · automatic checksum · ECU pinouts. Bench validation pending.</p></div><a class="xdf-download" href="https://github.com/terrafirma2021/yamaha-xt660/releases/download/v0.2.2/yamaha-xt660-windows.zip">Download ZIP</a></section>
<section class="download-bundle"><div><h2>Windows ECU emulator</h2><p>Five complete BINs · virtual cockpit · sensor faults · diagnostics</p><p>Native Windows runtime. No Python or WSL required. Nominal 16 MHz timing profile.</p></div><a class="xdf-download" href="https://github.com/terrafirma2021/yamaha-xt660/releases/download/emulator-v0.1.5/xt660-emulator-windows-x64.zip">Download emulator</a></section>
<section id="xdf-selected" class="xdf-selected"></section>
<details class="xdf-guide"><summary>Using the files</summary><ol><li>Open the matching BIN and XDF in TunerPro.</li><li>Edit maps or apply/remove a feature patch. Save a separate BIN.</li><li>Connect with XT660.FileTool.exe and read a backup. Write ECU loads your edited BIN and corrects its checksum automatically.</li></ol><p>Map values are raw. Physical scaling remains incomplete. Feature patch application still needs native TunerPro validation; the byte recipes are software-tested.</p></details>
<h2 id="xdf-library-title">Individual files</h2><table class="downloads-table"><thead><tr><th>ECU / variant</th><th class="file-size">Bytes</th><th>Maps</th><th colspan="2">Files</th></tr></thead><tbody>'''+''.join(cards)+'''</tbody></table>
<p><a href="../flashing/">Bench connections</a> · <a href="../docs/firmware/XDF_DEFINITIONS.html">XDF validation</a> · <a href="https://github.com/terrafirma2021/yamaha-xt660/tree/main/flasher">Desktop source</a> · <a href="https://github.com/terrafirma2021/yamaha-xt660/releases/tag/v0.2.2">Release notes &amp; hashes</a></p>'''
    write('xdf/index.html', shell('Downloads', body, 'xdf/index.html', 'XDF', '<link rel="stylesheet" href="../assets/xdf.css">'))
    write('xdf/manifest.json', json.dumps(manifest, indent=2)+'\n')
    # Bookmark compatibility contains only navigation, never the retired editor.
    write('tune/index.html', '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=../xdf/"><title>XDF downloads</title></head><body><a href="../xdf/">XDF downloads</a></body></html>')
    body = '<div class="page-heading"><h1>ECU tools</h1><p><a href="../xdf/">XDF downloads</a> · <a href="../flashing/">Bench connections</a></p></div>'
    write('tools/index.html', shell('ECU tools', body, 'tools/index.html', 'XDF'))
