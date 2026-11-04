"""Package only registered, hash-checked BINs and generated definitions."""
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist'
PACKAGE = OUT / 'yamaha-xt660-windows'
README = '''YAMAHA XT660 — BINs, XDFs and Windows file tools

1. Open a matching BIN and XDF in TunerPro.
2. Edit maps or apply/remove a feature patch. Save a separate BIN.
3. Open that BIN in XT660.FileTool.exe and save a checksum-corrected copy.

All nine registered BINs are preserved unchanged. Their startup checksum may
fail in the original source; use a corrected copy. XDF map values are raw.
Features use reversible patches. Apply the whole patch. For speed offsets,
remove the current offset patch before applying another. Early BINs have no
supported O2 switch. Correct the startup checksum after any edit.

The Windows tool is an unsigned file-tools preview. ECU reading and flashing
are not implemented. It opens no COM port and sends no ECU commands.
Map import/edit/save was checked in TunerPro for both file formats. Feature
patch XML, byte recipes and reversibility are software-tested; native TunerPro
patch application and physical ECU operation still need validation.

Source and findings: https://github.com/terrafirma2021/yamaha-xt660
Reference site: https://terrafirma2021.github.io/yamaha-xt660/
'''


def build():
    subprocess.run(['node', 'scripts/build_xdfs.mjs', '--check'], cwd=ROOT, check=True)
    records = json.loads((ROOT/'definitions/manifest.json').read_text(encoding='utf-8'))
    catalog = {i['id']: i for i in json.loads((ROOT/'analysis/firmware/catalog.json').read_text(encoding='utf-8'))['images']}
    PACKAGE.mkdir(parents=True, exist_ok=True)
    (PACKAGE/'bins').mkdir(exist_ok=True)
    (PACKAGE/'xdf').mkdir(exist_ok=True)
    files = {}
    for r in records['definitions']:
        for src, target, expected in [(r['bin_file'], 'bins/'+r['id']+'.bin', r['bin_sha256']), (r['file'], 'xdf/'+r['id']+'.xdf', r['xdf_sha256'])]:
            data = (ROOT/src).read_bytes()
            assert hashlib.sha256(data).hexdigest() == expected, src
            files[target] = data
        r['bin_file'], r['file'], r['code_family'] = 'bins/'+r['id']+'.bin', 'xdf/'+r['id']+'.xdf', catalog[r['id']]['code_family']
    files['XT660.FileTool.exe'] = (ROOT/'flasher/build/XT660.FileTool.exe').read_bytes()
    files['manifest.json'] = (json.dumps(records, indent=2)+'\n').encode()
    files['README.txt'] = README.encode()
    files['SHA256SUMS.txt'] = ''.join(hashlib.sha256(data).hexdigest()+'  '+path+'\n' for path,data in sorted(files.items())).encode()
    # Write an explicit allow-list; stale output is never swept into the ZIP.
    for path,data in files.items():
        (PACKAGE/path).write_bytes(data)
    archive = OUT/'yamaha-xt660-windows.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for path,data in sorted(files.items()):
            info=zipfile.ZipInfo('yamaha-xt660/'+path,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,data)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (OUT/'SHA256SUMS.txt').write_text(digest+'  '+archive.name+'\n',encoding='utf-8',newline='\n')
    print(f'Packaged {len(records["definitions"])} BIN/XDF pairs and Windows file tool: {archive}')


if __name__ == '__main__':
    build()
