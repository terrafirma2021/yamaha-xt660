"""Build the existing HC12 core for a browser worker with Emscripten 4.0.23."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from build import COMMIT, URL, apply_local_patches
from build_windows import DEPENDENCIES

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
VERSION='4.0.23'

def run(*args,cwd=None):
    print(' '.join(map(str,args)),flush=True)
    subprocess.run(list(map(str,args)),cwd=cwd,check=True)

def build(directory,output,jobs):
    directory=directory.resolve();output=output.resolve()
    if VERSION not in subprocess.check_output(['em++','--version'],text=True):
        raise RuntimeError('Activate Emscripten '+VERSION)
    if not directory.exists():run('git','clone','--depth','1','--branch','ucsim-0.9.12',URL,directory)
    if (directory/'.xt660-source.json').exists():
        archived=json.loads((directory/'.xt660-source.json').read_text())
        if archived['commit']!=COMMIT:raise RuntimeError('Wrong source archive')
        for name,digest in archived['files'].items():
            if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('Changed archived source: '+name)
    else:
        if subprocess.check_output(['git','rev-parse','HEAD'],cwd=directory,text=True).strip()!=COMMIT:
            raise RuntimeError('Use a fresh directory for the pinned uCsim source')
        apply_local_patches(directory)
    deps=HERE/'.build/deps';deps.mkdir(parents=True,exist_ok=True)
    import urllib.request
    url,digest=DEPENDENCIES['json.hpp'];header=deps/'json.hpp'
    if not header.exists():header.write_bytes(urllib.request.urlopen(url,timeout=30).read())
    if hashlib.sha256(header.read_bytes()).hexdigest()!=digest:raise RuntimeError('JSON header hash mismatch')
    config={'emscripten':VERSION,'commit':COMMIT,'flags':'-O3 -flto -fwasm-exceptions -DNDEBUG',
            'patches':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((HERE/'patches').glob('*.patch'))}}
    stamp=directory/'.xt660-wasm.json'
    if not stamp.exists() or json.loads(stamp.read_text())!=config:
        if not (directory/'Makefile').exists():
            run('emconfigure','./configure','--host=wasm32-unknown-emscripten','--enable-m68hc12-sim','--disable-serio',cwd=directory)
        elif 'em++' not in (directory/'src/common.mk').read_text():raise RuntimeError('Use a separate WASM build directory')
        run('make','preps',cwd=directory)
        run('make','-B',f'-j{jobs}','CXXFLAGS='+config['flags'],'libs',cwd=directory)
        sim=directory/'src/sims/m68hc12.src'
        run('make','-B',f'-j{jobs}','CXXFLAGS='+config['flags'],'m68hc12.o','imov.o','ialu.o','ibranch.o','iother.o','glob.o','glob12.o','dis.o','hcwrap.o',cwd=sim)
        stamp.write_text(json.dumps(config))
    sim=directory/'src/sims/m68hc12.src';output.mkdir(parents=True,exist_ok=True)
    includes=[deps,sim]+[directory/'src/core'/p for p in ['utils.src','sim.src','cmd.src','gui.src','motorola.src']]
    objects=[sim/(n+'.o') for n in ['m68hc12','imov','ialu','ibranch','iother','glob','glob12','dis','hcwrap']]
    data=HERE/'.build/wasm-data';data.mkdir(exist_ok=True)
    registry=json.loads((ROOT/'firmware/registry.json').read_text())
    for rel in ['firmware/registry.json']+[r['file'] for r in registry['images']]:
        dest=data/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,dest)
    for source,target,extra in [
        ('browser_bridge.cc','xt660.mjs',['-sEXPORTED_FUNCTIONS=["_xt_init","_xt_action","_xt_tick","_xt_state","_xt_cycles"]']),
        ('validate_native.cc','check.mjs',['-sEXPORTED_FUNCTIONS=["_main"]','-sINVOKE_RUN=0'])]:
        run('em++','-std=c++17','-O3','-flto','-fwasm-exceptions','--profiling-funcs','-DNDEBUG','-DXT660_DEFER_CLOCKS',*[f'-I{p}' for p in includes],
            HERE/'native'/source,*objects,f'-L{directory}',
            '-Wl,--start-group','-lmotorola','-lsim','-lucsimutil','-lgui','-lcmd','-Wl,--end-group',
            '-sMODULARIZE=1','-sEXPORT_ES6=1','-sENVIRONMENT=web,worker,node','-sALLOW_MEMORY_GROWTH=1',
            '-sINITIAL_MEMORY=33554432','-sSTACK_SIZE=1048576','-sFILESYSTEM=1',
            '-sEXPORTED_RUNTIME_METHODS='+json.dumps(['ccall','FS']+(['callMain'] if target=='check.mjs' else [])),
            '--preload-file',str(data)+'@/data',
            *extra,'-o',target,cwd=output)
    print(output)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--output',type=Path,default=ROOT/'dist/xt660-wasm');p.add_argument('--jobs',type=int,default=4)
    a=p.parse_args();build(a.directory,a.output,a.jobs)
