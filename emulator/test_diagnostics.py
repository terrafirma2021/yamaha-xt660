"""Dash holds, complete menu navigation and actuator timing through stock code."""
import argparse
import hashlib
import json
from pathlib import Path
from cockpit import Cockpit
from test_cockpit import until

MENU=[1,3,5,6,7,8,9,20,21,30,36,48,50,51,52,60,61,62,70]
ACTUATORS={30:('output',3,1),36:('output',6,1),48:('port_p',1,1),
           50:('port_a',2,1),51:('port_p',2,5),52:('port_p',4,5)}


def check(executable,wsl,image):
    b=Cockpit(executable,wsl)
    try:
        b.select(image);b.diagnostics(True)
        until(b,lambda:b.meter.mode=='diagnostic',180)
        assert b.meter.holds[0]['cycles']>=128000000
        assert b.meter.holds[1]['cycles']>=32000000
        holds=list(b.meter.holds)
        menu=MENU if b.engine.early else MENU[:-1]+[63,70]
        actuators=dict(ACTUATORS)
        if not b.engine.early:actuators[48]=('port_p',0,1)
        seen=[]
        for expected in menu:
            assert b.meter.diag_id==expected,(expected,b.meter.state())
            seen.append(b.meter.diag_id)
            b.diagnostic_next(1)
        assert b.meter.diag_id==1
        for expected in reversed(menu):
            b.diagnostic_next(-1)
            assert b.meter.diag_id==expected,(expected,b.meter.state())
        tests=[]
        for number,(kind,channel,period) in actuators.items():
            while b.meter.diag_id!=number:b.diagnostic_next(1)
            b.diagnostic_test(True)
            start=b.engine.cycles
            edges={}
            warnings=0
            while b.engine.cycles-start<(5*period+1)*16000000:
                b.engine.step(1000000)
                b.meter.poll(b.engine.exchange)
                warnings+=bool(b.meter.state()['warning'])
                for e in b.engine.trace:
                    if e['cycle']>start and e['kind']==kind and e['channel']==channel:
                        edges[e['cycle']]=e['value']
            levels=list(edges.values())
            # Keep the complete emitted transition list, including any initial
            # relay setup edge. Verify pulse count/cadence from the real output.
            rises=[t for t,v in edges.items() if v]
            falls=[t for t,v in edges.items() if not v]
            assert len(rises)==5 and len(falls)==5,(image,number,edges)
            assert warnings,(image,number,'no serial warning')
            assert all(abs((z-a)/16000000-period)<.02 for a,z in zip(rises,rises[1:])),(number,edges)
            tests.append(dict(number=number,kind=kind,channel=channel,
                              transitions=[dict(cycle=t-start,level=v) for t,v in edges.items()],
                              period_seconds_nominal=period,warning_replies=warnings))
            print('Diagnostic actuator PASS '+image+' d:'+str(number),flush=True)
            b.diagnostic_test(False)
        unchanged=b.engine.verify_flash()
        b.diagnostics(False)
        assert b.meter.mode=='normal' and b.meter.frames>0
        return dict(image=image,holds=holds,menu_forward_and_reverse=seen,
                    actuators=tests,normal_mode_after_exit=True,flash_bytes_unchanged=unchanged)
    finally:b.power(False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ucsim',required=True);p.add_argument('--wsl',action='store_true')
    p.add_argument('--image',required=True);a=p.parse_args()
    report=check(a.ucsim,a.wsl,a.image)
    here=Path(__file__).resolve().parent
    report['source_hashes']={p.relative_to(here).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (here/'cockpit.py',here/'meter.py',here/'engine.py',here/'native/xt660_boot.cc',Path(__file__))}
    (here/('diagnostic-validation-'+a.image+'.json')).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
