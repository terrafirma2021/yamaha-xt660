"""Cockpit integration uses external pins and checked serial replies only."""
import argparse
import hashlib
import json
from pathlib import Path
from cockpit import Cockpit, intake_fixture
from dashboard import available_images
from meter import MeterPeer


def until(bike,predicate,limit=45):
    for _ in range(limit):
        bike.tick()
        if predicate():
            return
    raise AssertionError(bike.state())


def test_cockpit(executable,wsl):
    for pitch in (500,1800,2800):
        assert intake_fixture(0,pitch,False)==(512,0)
        assert intake_fixture(0,pitch,True)[1]>intake_fixture(100,pitch,True)[1]
    assert intake_fixture(0,500,True)[1]>intake_fixture(0,2800,True)[1]
    peer=MeterPeer()
    peer.accept([42,17,149,57,9])
    assert peer.state()['fault']==21 and peer.state()['speed_pulses']==17
    before=peer.state()
    for frame in ([42,17,149,57,8],[1,2,3], [0,0,64,255,63]):
        try:peer.accept(frame)
        except ValueError:pass
        else:raise AssertionError('Bad frame accepted')
        assert peer.state()==before
    reports=[]
    for image in available_images():
        b=Cockpit(executable,wsl)
        try:
            b.select(image['id']);b.power(True)
            assert b.meter.frames==1 and b.meter.frame[0]==0
            b.start();until(b,lambda:b.rotating,24)
            until(b,lambda:b.pitch==1800)
            idle=b.meter.frame[0]
            assert idle>0
            sustained=[]
            for throttle in (0,100,0):
                b.control('throttle',throttle)
                for _ in range(100):
                    b.tick()
                    assert b.rotating,(image['id'],throttle,b.state())
                    assert b.meter.state()['fault']==0,(image['id'],throttle,b.state())
                sustained.append(b.meter.frame[:])
            b.control('gear',1);b.control('throttle',65)
            until(b,lambda:b.pitch==955)
            until(b,lambda:b.meter.frame[0]>idle and b.meter.frame[1]>0)
            moving=b.meter.frame[:]
            b.control('gear',0)
            until(b,lambda:b.meter.frame[1]==0)
            b.control('run',False)
            until(b,lambda:b.meter.frame[0]==0)
            assert not b.rotating and not b.engine.snapshot()['counts']['pulse_running']
            b.control('coolant',80)
            until(b,lambda:b.meter.frame[3]>=136)
            hot=b.meter.frame[3]
            b.control('coolant',512)
            until(b,lambda:b.meter.frame[3]<136)
            flash=b.engine.verify_flash()
            reports.append(dict(image=image['id'],authentication=b.auth,idle_code=idle,
                                sustained_idle_wot_idle_replies=sustained,
                                in_gear_reply=moving,hot_code=hot,flash_bytes_unchanged=flash,
                                checks=['key-on','starter and firing','throttle','VSS input through serial',
                                        'neutral stops road pulses','run switch stops engine','coolant via serial']))
            print('Cockpit PASS '+image['id'],flush=True)
        finally:b.power(False)
    return reports


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ucsim',required=True);p.add_argument('--wsl',action='store_true');a=p.parse_args()
    report=dict(cockpit=test_cockpit(a.ucsim,a.wsl))
    here=Path(__file__).resolve().parent
    report['source_hashes']={p.relative_to(here).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in [here/'cockpit.py',here/'meter.py',here/'engine.py',here/'native/xt660_boot.cc',Path(__file__)]}
    (here/'cockpit-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
