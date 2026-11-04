"""Unchanged firmware integration: external storage, serial peers and crank."""
import json
import threading
import urllib.error
import urllib.request
from dashboard import Dashboard, make_server, available_images
from engine import Engine
from runner import RUNS


def test_engine(executable,wsl):
    results=[]
    for image in available_images():
        with Engine(executable,image['id'],wsl) as ecu:
            if ecu.authentication_required:
                ecu.authenticate()
            ecu.exchange(0xfe)
            ecu.exchange(1)
            ecu.crank(patterns=12)
            for _ in range(25):
                ecu.step(100000)
                state=ecu.snapshot()
                if not state['counts']['pulse_running']:
                    break
            assert state['counts']['pulses']==132,state
            assert state['synchronized'] and state['pitch_ticks']==1600,state
            assert (state['authentication_complete'] or not ecu.authentication_required) and not state['authentication_inhibit'],state
            assert not any(state['faults']),state
            for ch in (3,6):
                edges=[e for e in ecu.trace if e['kind']=='output' and e['channel']==ch]
                assert len(edges)>=12,(image, ch, edges)
                assert all(a['value']!=b['value'] for a,b in zip(edges,edges[1:])),edges
            ecu.stop_crank()
            for _ in range(15):
                ecu.step(100000)
            lost=ecu.snapshot()
            assert not lost['synchronized'] and lost['pitch_ticks']==65535,lost
            unchanged=ecu.verify_flash()
            results.append(dict(image=image['id'],authentication='accepted' if ecu.authentication_required else 'disabled by BIN',meter_reply=ecu.transcript[-1],
                                crank_pulses=state['counts']['pulses'],pitch_ticks=state['pitch_ticks'],
                                output_transitions=state['output_transitions'],pulse_loss='detected',flash_bytes_unchanged=unchanged))
            print('Engine PASS '+image['id'],flush=True)
    for image in ('xt660-2004-2006-companion','xt660-2c1-10'):
        with Engine(executable,image,wsl) as ecu:
            ecu.authenticate(corrupt=True)
            assert not ecu.snapshot()['authentication_complete']
            ecu.verify_flash()
            results.append(dict(image=image,authentication='corrupt response rejected'))
    return results


def test_dashboard_http():
    dashboard=Dashboard('unused')
    server=make_server(dashboard,0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}'
    checks=[]
    try:
        with urllib.request.urlopen(url) as response:
            html=response.read().decode()
            assert dashboard.token in html and "script-src 'self'" in response.headers['Content-Security-Policy']
        checks.append('local assets and restrictive CSP')
        with urllib.request.urlopen(url+'/api/state') as response:
            state=json.load(response)
            assert not state['loaded'] and len(state['images'])==5,state
        checks.append('only five complete hash-checked BINs offered')
        for name,headers,body,status in [
            ('missing token',{}, {'action':'step'},403),
            ('cross origin',{'X-XT660-Token':dashboard.token,'Origin':'https://example.org'}, {'action':'step'},403),
            ('DNS rebinding',{'X-XT660-Token':dashboard.token,'Host':'example.org'}, {'action':'step'},403),
            ('no BIN',{'X-XT660-Token':dashboard.token},{'action':'step'},400),
            ('unknown BIN',{'X-XT660-Token':dashboard.token},{'action':'load','image':'../../../secret'},400)]:
            req=urllib.request.Request(url+'/api/action',json.dumps(body).encode(),headers)
            try:
                urllib.request.urlopen(req)
                raise AssertionError(name+' accepted')
            except urllib.error.HTTPError as error:
                assert error.code==status,(name,error.code)
            checks.append(name+' rejected')
        for path in ('/../firmware/registry.json','/storage.bin','/trace.csv'):
            try:
                urllib.request.urlopen(url+path)
                raise AssertionError(path+' exposed')
            except urllib.error.HTTPError as error:
                assert error.code==404
        checks.append('no arbitrary paths or downloads before load')
    finally:
        server.shutdown();server.server_close();thread.join();dashboard.close()
    return checks
