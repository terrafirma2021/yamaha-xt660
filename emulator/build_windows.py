"""Cross-build a standalone Windows x64 runtime; Python/WSL are build tools only."""
import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from build import COMMIT, URL, apply_local_patches

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEPENDENCIES = {
    'json.hpp': ('https://raw.githubusercontent.com/nlohmann/json/v3.11.3/single_include/nlohmann/json.hpp',
                 '9bea4c8066ef4a1c206b2be5a36302f8926f7fdc6087af5d20b417d0cf103ea6'),
    'httplib.h': ('https://raw.githubusercontent.com/yhirose/cpp-httplib/v0.18.1/httplib.h',
                 'f870541e065de607c8a7f64fc8743b475cd1388fff5238afa8841f75dcbf2b89'),
}


def run(*args, cwd=None):
    print(' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=cwd, check=True)


def build(directory, output, jobs):
    directory=directory.resolve();output=output.resolve()
    compiler='x86_64-w64-mingw32-g++-posix'
    if not shutil.which(compiler):
        raise SystemExit('Install MinGW-w64 POSIX C++ cross compiler, make, autoconf, flex, bison and Git on the build host.')
    if not directory.exists():
        run('git','clone','--branch','ucsim-0.9.12','--depth','1',URL,directory)
    # Corresponding-source bundles include the already patched upstream tree.
    if (directory/'.xt660-source.json').exists():
        manifest=json.loads((directory/'.xt660-source.json').read_text())
        if manifest['commit']!=COMMIT:raise RuntimeError('Wrong source archive')
        for name,digest in manifest['files'].items():
            if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=digest:
                raise RuntimeError('Changed archived source: '+name)
    else:
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=directory,text=True).strip()
        if head!=COMMIT:raise RuntimeError('Use a clean directory for pinned uCsim '+COMMIT)
        apply_local_patches(directory)
    deps=HERE/'.build/deps';deps.mkdir(parents=True,exist_ok=True)
    for name,(url,digest) in DEPENDENCIES.items():
        target=deps/name
        if not target.exists():target.write_bytes(urllib.request.urlopen(url,timeout=30).read())
        if hashlib.sha256(target.read_bytes()).hexdigest()!=digest:raise RuntimeError('Dependency hash mismatch: '+name)
    for name,url in {
        'json-LICENSE.MIT':'https://raw.githubusercontent.com/nlohmann/json/v3.11.3/LICENSE.MIT',
        'httplib-LICENSE':'https://raw.githubusercontent.com/yhirose/cpp-httplib/v0.18.1/LICENSE',
    }.items():
        if not (deps/name).exists():(deps/name).write_bytes(urllib.request.urlopen(url,timeout=30).read())
    stamp=directory/'.xt660-windows-build.json'
    config={'target':'x86_64-w64-mingw32','flags':'-O3 -g -flto -DNDEBUG -pipe','commit':COMMIT,
            'patches':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((HERE/'patches').glob('*.patch'))}}
    if not stamp.exists() or json.loads(stamp.read_text())!=config:
        if (directory/'Makefile').exists():
            # Existing cross build is usable only if it names the right toolchain.
            if compiler not in (directory/'src/common.mk').read_text():raise RuntimeError('Use a separate Windows build directory')
        else:
            run('./configure','--host=x86_64-w64-mingw32','CC=x86_64-w64-mingw32-gcc',
                'CXX='+compiler,'AR=x86_64-w64-mingw32-ar','RANLIB=x86_64-w64-mingw32-ranlib',
                '--enable-m68hc12-sim','--disable-serio',cwd=directory)
        run('make','preps',cwd=directory)
        run('make','-B',f'-j{jobs}','CXXFLAGS='+config['flags'],'libs',cwd=directory)
        run('make','-B',f'-j{jobs}','CXXFLAGS='+config['flags'],'-C','src/sims/m68hc12.src',cwd=directory)
        stamp.write_text(json.dumps(config))
    output.mkdir(parents=True,exist_ok=True)
    sim=directory/'src/sims/m68hc12.src'
    includes=[deps,sim]+[directory/'src/core'/n for n in ['utils.src','sim.src','cmd.src','gui.src','motorola.src']]
    objects=[sim/(n+'.o') for n in ['m68hc12','imov','ialu','ibranch','iother','glob','glob12','dis','hcwrap']]
    for source,exe in [('dashboard_native.cc','XT660.Emulator.exe'),('validate_native.cc','XT660.Emulator.Check.exe'),('xt660_boot.cc','XT660.Core.exe')]:
        run(compiler,'-std=c++17','-O3',f'-flto={jobs}','-DNDEBUG',*[f'-I{x}' for x in includes],
            HERE/'native'/source,*objects,f'-L{directory}',
            '-Wl,--start-group','-lmotorola','-lsim','-lucsimutil','-lgui','-lcmd','-Wl,--end-group',
            '-lshell32','-lws2_32','-lbcrypt','-lcrypt32','-static','-static-libgcc','-static-libstdc++','-o',output/exe)
        run('x86_64-w64-mingw32-strip',output/exe)
    package(directory,output,deps)


def package(directory,output,deps):
    # Preserve the existing relative registry paths. Source BINs are copied unchanged.
    registry=json.loads((ROOT/'firmware/registry.json').read_text())
    files=[ROOT/'firmware/registry.json',ROOT/'site/assets/yamaha-motor-logo.png',HERE/'COPYING']
    files += [p for p in (HERE/'native-validation.json',HERE/'windows-core-validation.json') if p.exists()]
    files += [ROOT/r['file'] for r in registry['images']]
    files += list((HERE/'web').glob('*'))
    for src in files:
        if src.is_file():
            dest=output/src.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
    licenses=output/'licenses';licenses.mkdir(exist_ok=True)
    for name in ('json-LICENSE.MIT','httplib-LICENSE'):shutil.copy2(deps/name,licenses/name)
    (output/'START-HERE.txt').write_text(
        'XT660 native Windows emulator\n\nRun XT660.Emulator.exe, then select an ECU and turn the key.\n'
        'No Python, WSL or installation is needed. Keep the extracted folder together.\n'
        'The executable runs the MCU independently; the browser reads snapshots and sends controls.\n'
        'Closing the browser does not stop the MCU. Close the emulator process to stop it.\n'
        'The nominal timing profile is 16 MHz. Physical oscillator/engine timing is not validated.\n'
        'No physical ECU/COM connection. BINs without boot code cannot run.\n\n'
        'Source: https://github.com/terrafirma2021/yamaha-xt660/tree/main/emulator\n'
        'uCsim HC12: Daniel Drotos; GPL-2.0-or-later (emulator/COPYING).\n'
        'JSON and HTTP libraries: MIT (licenses/).\n',encoding='utf-8')
    manifest={p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
              for p in output.rglob('*') if p.is_file() and p.name!='SHA256SUMS.json'}
    (output/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2)+'\n')
    archive=output.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(output.rglob('*')):
            if p.is_file():z.write(p,output.name+'/'+p.relative_to(output).as_posix())
    # Complete corresponding build sources, including the patched pinned core
    # and exact dependency headers. No Git metadata or compiled objects.
    source_archive=output.with_name(output.name+'-source').with_suffix('.tar.gz')
    source_files={}
    if (directory/'.xt660-source.json').exists():
        names=json.loads((directory/'.xt660-source.json').read_text())['files']
    else:names=subprocess.check_output(['git','ls-files'],cwd=directory,text=True).splitlines()
    import io
    with tarfile.open(source_archive,'w:gz') as tar:
        for name in names:
            p=directory/name
            if p.is_file():
                tar.add(p,'source/ucsim/'+name,recursive=False);source_files[name]=hashlib.sha256(p.read_bytes()).hexdigest()
        metadata=json.dumps({'commit':COMMIT,'files':source_files}).encode();entry=tarfile.TarInfo('source/ucsim/.xt660-source.json');entry.size=len(metadata);tar.addfile(entry,io.BytesIO(metadata))
        for p in HERE.rglob('*'):
            rel=p.relative_to(HERE)
            if p.is_file() and not any(part.startswith('.') or part=='__pycache__' for part in rel.parts):tar.add(p,'source/emulator/'+rel.as_posix(),recursive=False)
        for p in deps.glob('*'):
            if p.is_file():tar.add(p,'source/emulator/.build/deps/'+p.name,recursive=False)
        for p in files:
            if p.is_file() and not p.is_relative_to(HERE):tar.add(p,'source/'+p.relative_to(ROOT).as_posix(),recursive=False)
    print(archive);print(source_archive)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'dist/xt660-emulator-windows-x64')
    parser.add_argument('--jobs',type=int,default=4)
    parser.add_argument('--package-only',action='store_true',help='Repackage the exact executable and sources from native-validation.json')
    args=parser.parse_args()
    if args.package_only:
        report=json.loads((HERE/'native-validation.json').read_text())
        if hashlib.sha256((args.output/'XT660.Emulator.exe').read_bytes()).hexdigest()!=report['exe_sha256']:
            raise RuntimeError('Executable differs from the validated build')
        for name,digest in report['source_hashes'].items():
            if name.startswith(('native/','web/')) and hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=digest:
                raise RuntimeError('Runtime source changed since validation: '+name)
        package(args.directory.resolve(),args.output.resolve(),HERE/'.build/deps')
    else:
        build(args.directory,args.output,args.jobs)
