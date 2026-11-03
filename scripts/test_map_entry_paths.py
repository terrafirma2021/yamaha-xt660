"""Check previously unspecified early-map entry and fault paths against CPU12.

The five early-family BINs share these instructions. Later-family entry gates
are not inferred from them. Synthetic fixtures change RAM, never BIN files.
"""
import argparse
import hashlib
import json
import random
from pathlib import Path

from test_firmware_lookups import load_code, rd, wr
from test_input_coordinates import reset
from test_speed_sources import Replay

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'analysis/firmware/map_entry_validation.json'


def curve(m,base,value):
    q=max(0,min(m[base+1],value-m[base]))*m[base+2]
    i,f=divmod(q,256);a=m[base+3+i]
    return a if not f else (a*256+(m[base+4+i]-a)*f)//256


def throttle_fault(r):
    for flags in range(256):
        m=reset(r);m[0x8AF]=flags;wr(m,0x8E8,2,12345);wr(m,0x4E62,2,23456)
        r.run((0x7DE6,0x7E04))
        assert rd(r.reg,0,2)==(23456 if flags&12 and flags&48 else 12345)
    return 256


def startup_delay(r):
    for n in range(1024):
        m=reset(r);temperature=n%256;flags=(0,16,64,80)[n//256]
        start=bool(n%2);disabled=bool((n//2)%2)
        threshold=curve(m,0x18B6,temperature)
        count=max(0,min(255,threshold+(-1,0,1)[(n//4)%3]))
        m[0x881],m[0x9A1],m[0x18B5],m[0x8F4],m[0xCAF]=16 if start else 0,flags,128 if disabled else 0,temperature,count
        m[0xCAE]=77
        lookup=not start and not flags&16 and not disabled
        set_flag=not start and (bool(flags&16) or (not disabled and threshold<=count))
        r.run((0x6B49,0x6B74))
        assert m[0xCAE]==(threshold if lookup else 77)
        assert m[0x9A1]==(flags|64 if set_flag else flags)
    return 1024


def adaptive(r,rng):
    changes=[(0x881,1,16),(0x8F4,1,63),(0x9B5,1,0),(0x886,1,64),(0x9A1,1,0),
             (0x992,2,1),(0x97A,1,127),(0x896,1,0),(0x8A0,1,32),
             (0x982,2,99),(0x982,2,100),(0x982,2,200),(0x982,2,201),
             (0x8F2,2,99),(0x8F2,2,100),(0x8F2,2,101),(0x8F2,2,199),(0x8F2,2,200)]
    changes += [(a,1,1<<bit) for a in (0x8AF,0x8B0,0x8B1) for bit in range(8)]
    for n in range(512):
        m=reset(r)
        m[0x8F4],m[0x9B5],m[0x97A],m[0xD87],m[0x896],m[0x9A1]=128,255,128,9,16,64
        m[0x357E],m[0x357D],m[0x9AD]=64,10,(9,10,11,255)[n%4]
        for a,v in [(0x3584,100),(0x3586,200),(0x3580,100),(0x3582,200),(0x8F2,300),(0x982,150)]:wr(m,a,2,v)
        m[0x35B0:0x3614]=bytes([0 if n%11==0 else 1])*100
        m[0x363C:0x36A0]=bytes([0 if n%13==0 else 128])*100
        if n%3:
            a,width,value=changes[(n//3)%len(changes)];wr(m,a,width,value)
        m[0x9A2]=128 if n%2 else 0
        flags=m[0x9A1];count=m[0x9AD]
        p=rd(m,0x8F2,2)
        pressure=True if p>=200 else False if p<=100 else bool(m[0x9A2]&128)
        qualified=(not m[0x881]&16 and curve(m,0x36C4,m[0x8F4])<=m[0x9B5] and m[0x8F4]>=64
                   and n%11!=0 and n%13!=0 and not m[0x886]&64 and bool(flags&64)
                   and rd(m,0x992,2)==0 and m[0x97A]==128 and not (m[0xD87]==9 and not m[0x896]&16)
                   and not m[0x8AF]&60 and not m[0x8B0]&192 and not m[0x8B1]&192
                   and 100<=rd(m,0x982,2)<=200 and pressure and not m[0x8A0]&32)
        r.run((0xA564,0xA63A))
        assert bool(m[0x9A2]&128)==pressure
        assert m[0x9A1]==(flags|128 if qualified and count>=10 else flags&~128),(n,qualified,count)
        assert m[0x9AD]==(count if qualified else 0)
    return 512


def pair(r,rng):
    changes=[(0x8F4,1,63),(0x992,2,257),(0x982,2,201),(0x881,1,32),
             (0x4E10,1,0),(0x4E11,1,0),(0x9A1,1,128),(0x8A0,1,32),
             (0x8B0,1,16),(0x8B0,1,4),(0x8B0,1,2),(0x8B1,1,128),(0x8B1,1,64)]
    for n in range(512):
        m=reset(r);m[0xD87]=9 if n%17 else 0;m[0x896]=0 if n%2 else 16;m[0x898]=0
        m[0x8F4],m[0x4C03],m[0x4C04],m[0x4E10],m[0x4E11],m[0x4C02]=128,64,1,1,1,3
        wr(m,0x992,2,256);wr(m,0x982,2,100);wr(m,0x4C06,2,200)
        m[0x4C44:0x4D0C]=bytes([0 if n%11==0 else 1])*200
        m[0x4D48:0x4E10]=bytes([0 if n%13==0 else 128])*200
        m[0xACF]=(0,2,3,4,255)[n%5]
        if n%3:
            a,width,value=changes[(n//3)%len(changes)];wr(m,a,width,value)
        if n%19==0:m[0x8A0]|=4;m[0xBDD]=m[0xD49]
        port,flag=rng.randrange(256),rng.randrange(256);m[0xF0],m[0x889]=port,flag
        count=m[0xACF];bypass=bool(m[0x8A0]&4 and m[0xBDD]==m[0xD49]);command=False
        if not bypass and m[0xD87]==9:
            qualified=(m[0x8F4]>=64 and rd(m,0x992,2)<=256 and rd(m,0x982,2)<=200 and not m[0x881]&32
                       and bool(m[0x4E10] if not m[0x896]&16 else m[0x4E11+m[0x898]])
                       and n%11!=0 and n%13!=0)
            reached=qualified and count>=3;count=min(255,count+1) if qualified else 0
            command=reached or bool(m[0x9A1]&128 or m[0x8A0]&32 or m[0x8B0]&22 or m[0x8B1]&192)
        r.run((0x9CAE,0x9D61))
        assert m[0xACF]==count,(n,qualified if not bypass and m[0xD87]==9 else None)
        assert m[0xF0]==(port if bypass else port|2 if command else port&~2)
        assert m[0x889]==(flag if bypass else flag|128 if command else flag&~128)
    return 512


def build():
    code=load_code('early');results=[]
    for e in json.loads((ROOT/'analysis/firmware/catalog.json').read_text())['images']:
        if e['code_family']!='early':continue
        raw=(ROOT/e['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==e['sha256']
        r=Replay(b'\xff'*e['base_address']+raw,code);rng=random.Random(660052)
        checks=dict(throttle_map_fault_substitution=throttle_fault(r),feedback_startup_delay=startup_delay(r),
                    adaptive_grid_eligibility=adaptive(r,rng),pair_grid_eligibility=pair(r,rng))
        results.append(dict(id=e['id'],firmware_sha256=e['sha256'],checks=checks,
                            instruction_addresses=[f'0x{a:04X}' for a in sorted(r.executed)]))
        print(e['id'],checks,flush=True)
    return dict(result='passed',cases=sum(sum(e['checks'].values()) for e in results),images=results,
                test_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                dependencies={n:hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest() for n in ['test_input_coordinates.py','test_speed_sources.py','test_firmware_lookups.py','test_full_lift.py']},
                limits=['Early application family only','Boundary/branch fixtures, not all combinations or concurrent ECU execution','No physical pin-level or sensor-unit verification'])


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args();result=build()
    if args.check:assert json.loads(REPORT.read_text())==result,'Map entry report is stale'
    else:REPORT.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Map entries:',result['cases'],'cases passed')
