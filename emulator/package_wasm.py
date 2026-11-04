"""Stage validated WASM assets, static cockpit and complete corresponding sources."""
import argparse
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from build_wasm import COMMIT, VERSION

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'scripts'))
from site_emulator import package

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def source_digest(path):return hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True,help='Patched upstream build tree')
    p.add_argument('--bundle',type=Path,default=ROOT/'dist/xt660-wasm')
    a=p.parse_args();runtime=HERE/'browser/runtime';runtime.mkdir(exist_ok=True)
    report=json.loads((HERE/'wasm-validation.json').read_text())
    for name in ('xt660.wasm','xt660.mjs','xt660.data'):
        assert digest(a.bundle/name)==report['artifacts'][name],('Unvalidated asset',name)
        shutil.copyfile(a.bundle/name,runtime/name)
    sources=[*sorted((HERE/'native').glob('*')),*sorted((HERE/'patches').glob('*.patch')),HERE/'build.py',HERE/'build_wasm.py',HERE/'build_windows.py',ROOT/'firmware/registry.json']
    manifest={'ucsim':COMMIT,'emscripten':VERSION,'artifacts':{p.name:digest(p) for p in runtime.iterdir() if p.suffix in ('.wasm','.mjs','.data')},
              'sources':{p.relative_to(ROOT).as_posix():source_digest(p) for p in sources}}
    (runtime/'build.json').write_text(json.dumps(manifest,indent=2)+'\n')
    static=ROOT/'dist/xt660-emulator-browser';package(static,runtime)
    shutil.copyfile(HERE/'COPYING',static/'COPYING')
    shutil.copyfile(HERE/'wasm-validation.json',static/'validation.json')
    (static/'START-HERE.txt').write_text('Open https://terrafirma2021.github.io/yamaha-xt660/emulator/\n\nTo host this package yourself, serve this folder over HTTP or HTTPS.\nFor example: python -m http.server 8767\nThen open http://127.0.0.1:8767/ in a current browser.\nThe HTTP server only delivers files; the ECU executes entirely in a browser worker.\nDo not open index.html through file://. No WSL or ECU server is required.\n\nClosing or refreshing the tab resets the simulation.\nSee validation.json, COPYING and licenses/ for test scope and licensing.\n',encoding='utf-8')
    shutil.make_archive(str(static),'zip',root_dir=static.parent,base_dir=static.name)
    archive=static.with_name(static.name+'-source').with_suffix('.tar.gz')
    names=subprocess.check_output(['git','ls-files'],cwd=a.directory,text=True).splitlines();upstream={}
    with tarfile.open(archive,'w:gz') as tar:
        for name in names:
            src=a.directory/name
            if src.is_file():tar.add(src,'source/ucsim/'+name,recursive=False);upstream[name]=digest(src)
        metadata=json.dumps({'commit':COMMIT,'files':upstream}).encode();entry=tarfile.TarInfo('source/ucsim/.xt660-source.json');entry.size=len(metadata);tar.addfile(entry,io.BytesIO(metadata))
        for src in HERE.rglob('*'):
            rel=src.relative_to(HERE)
            if src.is_file() and not any(part.startswith('.') or part in ('__pycache__','runtime') for part in rel.parts):
                tar.add(src,'source/emulator/'+rel.as_posix(),recursive=False)
        for name in ('json.hpp','json-LICENSE.MIT'):
            tar.add(HERE/'.build/deps'/name,'source/emulator/.build/deps/'+name)
        registry=json.loads((ROOT/'firmware/registry.json').read_text())
        for name in ['firmware/registry.json','scripts/site_emulator.py','site/assets/yamaha-motor-logo.png']+[r['file'] for r in registry['images']]:
            tar.add(ROOT/name,'source/'+name)
    print(static.with_suffix('.zip'));print(archive)
