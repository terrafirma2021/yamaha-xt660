"""Check active faults, EEPROM history and dash diagnostic commands end to end."""
import argparse
import hashlib
import json
from pathlib import Path
from cockpit import Cockpit
from test_cockpit import until


def check(executable,wsl,image):
    b=Cockpit(executable,wsl)
    try:
        b.select(image);b.power(True)
        b.control('fault','combined')
        until(b,lambda:{15,21}.issubset(b.meter.seen),200)
        seen=list(b.meter.seen)
        b.control('fault','none')
        until(b,lambda:b.meter.state()['fault']==0,160)
        for _ in range(6):b.tick()
        assert b.engine.snapshot()['counts']['eeprom_writes']>0
        before=b.engine.external_storage()
        b.diagnostics(True)
        until(b,lambda:b.meter.mode=='diagnostic',240)
        b.diagnostic_item(61)
        history=set()
        for _ in range(400):
            b.tick()
            if b.meter.diag_value:history.add(b.meter.diag_value)
            if {15,21}.issubset(history):break
        assert {15,21}.issubset(history),(history,b.meter.state())
        b.diagnostic_item(62)
        count=b.meter.diag_value
        assert count>=2,(count,b.meter.state())
        b.clear_history()
        until(b,lambda:b.meter.diag_value==0,80)
        for _ in range(6):b.tick()
        after=b.engine.external_storage()
        assert before!=after
        assert before[0x24:0x28]!=bytes(4) and after[0x24:0x28]==bytes(4),(before[0x24:0x28],after[0x24:0x28])
        assert b.engine.verify_flash()==59392
        result=dict(image=image,active_codes=seen,history_after_key_cycle=sorted(history),
                    stored_count=count,count_after_clear=b.meter.diag_value,
                    storage_changed=True,flash_bytes_unchanged=59392)
        print('Fault history PASS '+image,flush=True)
        return result
    finally:b.power(False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ucsim',required=True);p.add_argument('--wsl',action='store_true');a=p.parse_args()
    report=dict(faults=[check(a.ucsim,a.wsl,i) for i in
                       ('xt660-2004-2006-companion','xt660-2c1-10','xt660-2c1-10-immo-off')])
    here=Path(__file__).resolve().parent
    report['source_hashes']={p.relative_to(here).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (here/'cockpit.py',here/'meter.py',here/'engine.py',here/'native/xt660_boot.cc',Path(__file__))}
    (here/'cockpit-fault-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
