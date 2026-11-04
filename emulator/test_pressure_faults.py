"""Prove the external intake fixture does not bypass stock pressure faults."""
import argparse
import hashlib
import json
from pathlib import Path
from cockpit import Cockpit
from test_cockpit import until


def check(executable,wsl,image):
    b=Cockpit(executable,wsl)
    try:
        b.select(image);b.power(True);b.start()
        until(b,lambda:b.rotating and b.pitch==1800)
        for _ in range(30):b.tick()
        assert not any(b.engine.snapshot()['faults'])
        # Freeze only the external pressure waveform. Do not call the bike's
        # input updater, which would restore its throttle/speed-dependent dip.
        b.engine.session.command('set memory xtboot_0_cfg 39 0')
        for _ in range(120):
            b.engine.step(1000000)
            b.meter.poll(b.engine.exchange)
            if b.engine.snapshot()['faults'][0]&16:break
        else:raise AssertionError('Stuck pressure was not detected: '+image)
        assert b.meter.state()['warning']
        b.control('run',False)
        until(b,lambda:b.meter.state()['fault']==14,60)
        # Circuit qualification is in the crank-driven pressure sample path.
        # Exercise it in a fresh key cycle before reading the stopped fault.
        b.control('fault','pressure')
        b.power(False);b.power(True)
        b.control('run',True);b.start()
        for _ in range(30):b.tick()
        b.control('run',False)
        until(b,lambda:b.meter.state()['fault']==13,180)
        assert b.engine.verify_flash()==59392
        print('Pressure faults PASS '+image,flush=True)
        return dict(image=image,healthy_waveform=True,stuck_pressure_fault_bit=True,
                    warning_via_serial=True,disconnected_pressure_serial_code=13,
                    flash_bytes_unchanged=59392)
    finally:b.power(False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ucsim',required=True);p.add_argument('--wsl',action='store_true');a=p.parse_args()
    report=dict(pressure=[check(a.ucsim,a.wsl,i) for i in
                          ('xt660-2004-2006-companion','xt660-2c1-10')])
    here=Path(__file__).resolve().parent
    report['source_hashes']={p.relative_to(here).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (here/'cockpit.py',here/'engine.py',here/'native/xt660_boot.cc',Path(__file__))}
    (here/'pressure-fault-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
