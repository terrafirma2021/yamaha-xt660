"""Package only registered, hash-checked BINs and generated definitions."""
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist'
PACKAGE = OUT / 'yamaha-xt660-windows-v0.2.1'
README = '''YAMAHA XT660 — Windows Flash Tool, BINs and XDFs

XT660.FileTool.exe
  Connect: select your USB KKL COM port and follow the power prompts.
  Read ECU: save a backup checked against two independent reads.
  Write ECU: load a matching BIN, review the checksum and confirm.
  Pinouts page: choose the 26-pin or 34-pin ECU connector drawing.
  Light/dark mode: switch from the header; your choice is remembered.

Always keep a backup. Before writing, the tool saves two matching ECU reads
under %LOCALAPPDATA%/XT660/Backups. The loaded BIN is unchanged. Startup
checksum correction is automatic, and writes require byte-for-byte readback.
Only application CPU 1800-F7FF is programmed; the ECU boot is preserved.
Keep ECU power and USB connected until completion. No engine running.

This is a bench-test prerelease, not a hardware-qualified flashing tool.
Session entry, reads, writes and failure handling are software-tested against
the recovered XT boot format. Real ECU/adapter operation is not yet tested.
Unknown code layouts, incompatible ECU applications and unknown boot versions
block writing. No automatic erase/program retry is performed.

Edit with TunerPro using the matching BIN/XDF. All nine registered source BINs
are preserved unchanged; original startup sums may fail. Map values are raw.
Native TunerPro map editing was checked for both formats. Feature patch XML
and reversibility are software-tested; native patch application remains untested.

Source: https://github.com/terrafirma2021/yamaha-xt660/tree/main/flasher
Reference: https://terrafirma2021.github.io/yamaha-xt660/
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
    for name in ('barlow-OFL.txt','barlowcondensed-OFL.txt'):
        files['licenses/'+name] = (ROOT/'site/assets/fonts'/name).read_bytes()
    files['SHA256SUMS.txt'] = ''.join(hashlib.sha256(data).hexdigest()+'  '+path+'\n' for path,data in sorted(files.items())).encode()
    # Write an explicit allow-list; stale output is never swept into the ZIP.
    for path,data in files.items():
        (PACKAGE/path).parent.mkdir(parents=True, exist_ok=True)
        (PACKAGE/path).write_bytes(data)
    archive = OUT/'yamaha-xt660-windows.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for path,data in sorted(files.items()):
            info=zipfile.ZipInfo('yamaha-xt660/'+path,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,data)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (OUT/'SHA256SUMS.txt').write_text(digest+'  '+archive.name+'\n',encoding='utf-8',newline='\n')
    print(f'Packaged {len(records["definitions"])} BIN/XDF pairs and Windows Flash Tool: {archive}')


if __name__ == '__main__':
    build()
