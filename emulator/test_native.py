"""Windows runtime parity, headless pacing and loopback API checks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request

HERE=Path(__file__).resolve().parent


def compare(optimized,reference):
    assert len(optimized['images'])==len(reference['images'])==5
    for actual,expected in zip(optimized['images'],reference['images']):
        assert actual['image']==expected['image']
        for name in ('checkpoints','bad_key'):
            assert actual.get(name)==expected.get(name),(actual['image'],name)
    return sum(len(x['checkpoints'])+('bad_key' in x) for x in optimized['images'])


def http_checks(bundle,seconds=8):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    environment=os.environ.copy()
    # Runtime must work without Python, WSL or MinGW in PATH.
    environment['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
    child=subprocess.Popen([str(bundle/'XT660.Emulator.exe'),'--no-browser','--port',str(port)],
                           cwd=bundle,env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    def get(path='/api/state'):
        with urllib.request.urlopen(base+path,timeout=5) as r:return json.load(r)
    try:
        for _ in range(100):
            if child.poll() is not None:raise AssertionError(child.stderr.read().decode())
            try:
                html=urllib.request.urlopen(base,timeout=.2).read().decode();break
            except (OSError,urllib.error.URLError):time.sleep(.05)
        else:raise AssertionError('Native listener did not start')
        token=re.search(r'name="session" content="([^"]+)"',html)[1]
        def request(action,**values):
            req=urllib.request.Request(base+'/api/action',json.dumps(dict(action=action,**values)).encode(),
                                      {'Content-Type':'application/json','X-XT660-Token':token})
            with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
        assert get()['runtime']['native'] and not get()['loaded']
        for req in (urllib.request.Request(base+'/api/state',headers={'Host':'example.com'}),
                    urllib.request.Request(base+'/api/action',b'{"action":"load"}',{'Content-Type':'application/json'}),
                    urllib.request.Request(base+'/api/action',b'{"action":"load"}',{'X-XT660-Token':token,'Origin':'https://example.com'})):
            try:urllib.request.urlopen(req);raise AssertionError('Cross-origin control accepted')
            except urllib.error.HTTPError as e:assert e.code==403
        results=[]
        for image in get()['images']:
            request('load',image=image['id']);begin=time.perf_counter();s=request('key',enabled=True)
            key_seconds=time.perf_counter()-begin;request('start')
            start=time.perf_counter()
            while not get()['bike']['rotating']:
                assert time.perf_counter()-start<3;time.sleep(.05)
            start_seconds=time.perf_counter()-start
            s=request('control',name='throttle',value=100);request('control',name='gear',value=1)
            # Settle the physical-input fixture, then make NO requests during
            # the measurement. No tab or polling loop is advancing the MCU.
            time.sleep(1)
            before=get();begin=time.perf_counter();time.sleep(seconds);after=get();wall=time.perf_counter()-begin
            sim=(after['counts']['bus_cycles']-before['counts']['bus_cycles'])/16e6
            assert after['bike']['rotating'] and after['bike']['meter']['fault']==0 and not after['error'],after
            assert .93<=sim/wall<=1.07,(image['id'],sim,wall)
            assert after['bike']['meter']['frames']>before['bike']['meter']['frames']
            request('pause',paused=True);paused=get();time.sleep(.2)
            for _ in range(5):assert get()['counts']['bus_cycles']==paused['counts']['bus_cycles']
            stepped=request('tick');assert stepped['counts']['bus_cycles']>paused['counts']['bus_cycles']
            request('verify')
            try:request('control',name='throttle',value=101);raise AssertionError('Invalid throttle accepted')
            except urllib.error.HTTPError as e:assert e.code==400
            request('key',enabled=False)
            results.append(dict(image=image['id'],key_on_seconds=key_seconds,start_seconds=start_seconds,
                                no_client_wall_seconds=wall,no_client_simulated_seconds=sim,realtime_ratio=sim/wall,
                                valid_kline_replies=True,paused_reads_do_not_advance=True,flash_unchanged=True))
        return results
    finally:
        child.terminate();child.wait(timeout=10)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--reports',type=Path,default=HERE/'.runs')
    parser.add_argument('--reuse',action='store_true',help='Reuse completed native full/reference execution reports')
    args=parser.parse_args();bundle=args.bundle.resolve();reports=args.reports.resolve();reports.mkdir(exist_ok=True,parents=True)
    if not args.reuse:
        for mode,path,extra in [('optimized','native-full.json',['full']),('reference','native-reference.json',[])]:
            with (reports/(path+'.log')).open('w') as log:
                subprocess.run([str(bundle/'XT660.Emulator.Check.exe'),str(bundle),str(reports/path),mode,*extra],
                               stdout=log,stderr=subprocess.STDOUT,check=True)
    full=json.loads((reports/'native-full.json').read_text());reference=json.loads((reports/'native-reference.json').read_text())
    assert full['full'] and not full['reference'] and reference['reference']
    matched=compare(full,reference)
    result=dict(scope='Native Windows runtime; nominal 16 MHz pacing, not measured physical ECU timing',
                matched_reference_checkpoints=matched,execution=full['images'],headless=http_checks(bundle))
    result['source_hashes']={p.relative_to(HERE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [*sorted((HERE/'native').glob('*')),HERE/'web/dashboard.js',HERE/'build_windows.py',Path(__file__)] if p.is_file()}
    result['exe_sha256']=hashlib.sha256((bundle/'XT660.Emulator.exe').read_bytes()).hexdigest()
    (reports/'native-validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'matched_checkpoints':matched,'headless':result['headless']},indent=2))


if __name__=='__main__':main()
