"""Package the static, worker-owned ECU cockpit; no server or native process."""
from pathlib import Path
import shutil
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]

def verified_package(destination):
    runtime=ROOT/'emulator/browser/runtime'
    manifest=json.loads((runtime/'build.json').read_text())
    for name,digest in manifest['artifacts'].items():
        assert hashlib.sha256((runtime/name).read_bytes()).hexdigest()==digest,('Changed WASM asset',name)
    for name,digest in manifest['sources'].items():
        assert hashlib.sha256((ROOT/name).read_text(encoding='utf-8').encode()).hexdigest()==digest,('Rebuild WASM after source change',name)
    package(destination,runtime)
    for src,name in [(ROOT/'emulator/COPYING','COPYING'),(ROOT/'emulator/wasm-validation.json','validation.json')]:
        shutil.copyfile(src,Path(destination)/name)

def package(destination,runtime=None):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    runtime=Path(runtime or ROOT/'emulator/browser/runtime')
    # Version the complete executable chain. A cached worker otherwise loads
    # yesterday's WASM even when a normal reload refreshes index.html.
    inputs=[runtime/name for name in ('xt660.mjs','xt660.wasm','xt660.data')]
    inputs += [ROOT/'emulator/browser'/name for name in ('client.js','worker.js')]
    inputs += [ROOT/'emulator/web'/name for name in ('dashboard.js','dashboard.css','dashboard.html')]
    inputs += [Path(__file__)]
    digest=hashlib.sha256()
    for src in inputs:
        digest.update(src.read_bytes() if src.suffix in ('.wasm','.data') else src.read_text(encoding='utf-8').encode())
    version=digest.hexdigest()[:16]
    for name in ('xt660.mjs','xt660.wasm','xt660.data'):
        shutil.copyfile(runtime/name,destination/name)
    for p in (ROOT/'emulator/browser').glob('*.js'):
        code=p.read_text(encoding='utf-8')
        if p.name=='client.js':
            assert code.count("'worker.js'")==1
            code=code.replace("'worker.js'",f"'worker.js?v={version}'")
        elif p.name=='worker.js':
            assert code.count("'./xt660.mjs'")==1 and code.count('createCore({')==1
            code=code.replace("'./xt660.mjs'",f"'./xt660.mjs?v={version}'")
            code=code.replace('createCore({',"createCore({locateFile:name=>new URL(name+'?v="+version+"',import.meta.url).href,")
        (destination/p.name).write_text(code,encoding='utf-8')
    shutil.copytree(ROOT/'emulator/browser/licenses',destination/'licenses',dirs_exist_ok=True)
    for name in ('dashboard.js','cockpit.png','ignition-key.png'):
        shutil.copyfile(ROOT/'emulator/web'/name,destination/name)
    css=(ROOT/'emulator/web/dashboard.css').read_text(encoding='utf-8').replace("url('/cockpit.png')","url('cockpit.png')")
    (destination/'dashboard.css').write_text(css,encoding='utf-8')
    shutil.copyfile(ROOT/'site/assets/yamaha-motor-logo.png',destination/'logo.png')
    page=(ROOT/'emulator/web/dashboard.html').read_text(encoding='utf-8')
    for name in ('dashboard.css','dashboard.js','logo.png','cockpit.png','ignition-key.png'):
        page=page.replace('"/'+name+'"','"'+name+'"')
    page=page.replace('<script src="dashboard.js" defer>', '<script src="client.js" defer></script><script src="dashboard.js" defer>')
    for name in ('dashboard.css','dashboard.js','client.js'):
        page=page.replace('"'+name+'"',f'"{name}?v={version}"')
    page=page.replace('{{TOKEN}}','browser-worker')
    page=page.replace('LIVE FIRMWARE / LOCAL SIMULATION','LIVE FIRMWARE / BROWSER SIMULATION')
    page=page.replace('This local simulator needs JavaScript. All scripts and assets are served locally.',
        'The emulator needs JavaScript and WebAssembly. The research pages remain readable without scripts.')
    page=page.replace('Choose an ECU, then turn the key.</span>','Loading emulator…</span>',1)
    page=page.replace('<button id="load">','<button id="load" disabled>')
    page=page.replace('href="/trace.csv"','href="#"').replace('href="/storage.bin"','href="#"')
    page=page.replace('<footer>','<footer><span><a href="../">XT660 library</a> · <a href="https://github.com/terrafirma2021/yamaha-xt660/tree/main/emulator">Source &amp; licences</a></span>')
    (destination/'index.html').write_text(page,encoding='utf-8')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--destination',type=Path,required=True);p.add_argument('--runtime',type=Path)
    a=p.parse_args();package(a.destination,a.runtime)
