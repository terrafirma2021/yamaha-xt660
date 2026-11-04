"""Audit the second later-family lookup implementation and its fuel consumer.

Independent integer models versus byte-checked instructions in all four BINs.
Synthetic calibration values expose indexing/rounding hidden by constant maps;
they are memory-only fixtures, never modifications to the registered images.
"""
import argparse
import bisect
import hashlib
import json
import random
from pathlib import Path

from test_firmware_lookups import load_code, rd, wr
from test_speed_sources import Replay

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT/'analysis/firmware/late_transient_validation.json'
STORED = {0x3570:(0x3560,8),0x3578:(0x3560,8),0x3580:(0x3560,8),
          0x359A:(0x3588,9),0x35FE:(0x35EE,8),0x3618:(0x3606,9)}
UNIFORM = {0x35A6:(0x35A3,1),0x35C6:(0x35C3,1),0x35E6:(0x35E0,2)}


def reset(r):
    r.ram[:] = bytes(0x1800)+r.image[0x1800:]
    r.reg[:] = bytes(64)
    return r.ram


def call(r, pc):
    wr(r.ram,0x1700,2,0x17FE)
    r.run((pc,0x17FE))


def uniform(m, base, width, value):
    lo,span,factor = (rd(m,base+k*width,width) for k in range(3))
    q = min(span,max(0,value-lo))*factor
    if width == 2:
        q = min(65535,q//256)
    i,f = divmod(q,256)
    a = m[base+3*width+i]
    return a if not f else (a*256+(m[base+3*width+i+1]-a)*f)//256


def axis_index(m, base, count, value):
    axis = [rd(m,base+2*k,2) for k in range(count)]
    if value <= axis[0]: return 0
    if value >= axis[-1]: return (count-1)*256
    i = bisect.bisect_right(axis,value)-1
    fraction = ((value-axis[i])*65536//(axis[i+1]-axis[i])+128)//256
    return i*256+fraction


def stored_q8(m, data, value):
    axis,count = STORED[data]
    i,f = divmod(axis_index(m,axis,count,value),256)
    return m[data+i]*256 if not f else m[data+i]*256+(m[data+i+1]-m[data+i])*f


def stored(m, data, value):
    return (stored_q8(m,data,value)+128)//256


def helper_cases(r, maps):
    count = 0
    for m in maps:
        data = int(m['data_address'],16)
        if data not in STORED and data not in UNIFORM: continue
        assert len(m['calls']) >= 1, m['id']
        for synthetic in (False,True):
            mem = reset(r)
            if synthetic:
                mem[data:data+m['columns']] = bytes((19+197*k)%256 for k in range(m['columns']))
            if data in UNIFORM:
                base,width = UNIFORM[data]
                lo,span = rd(mem,base,width),rd(mem,base+width,width)
                points = set(range(256)) if width == 1 else {0,65535,lo,lo+span//2,lo+span}
                if width == 2:
                    points |= {max(0,min(65535,lo+k*4096+d)) for k in range(m['columns']) for d in (-1,0,1)}
                for v in sorted(points):
                    wr(r.reg,16,2,base)
                    wr(r.reg,0,width,v)
                    call(r,0xEF7F if width == 1 else 0xEE81)
                    assert r.reg[0] == uniform(mem,base,width,v),(m['id'],v)
                    count += 1
            else:
                base,n = STORED[data]
                points = {0,65535}|{max(0,min(65535,rd(mem,base+2*k,2)+d)) for k in range(n) for d in (-1,0,1)}
                points |= {(rd(mem,base+2*k,2)+rd(mem,base+2*k+2,2))//2 for k in range(n-1)}
                for v in sorted(points):
                    wr(mem,0xBC4,2,v);wr(mem,0xBC6,2,base);r.reg[0]=n
                    call(r,0xEFA4)
                    q = axis_index(mem,base,n,v)
                    assert rd(r.reg,0,2)==q,(m['id'],v,'axis')
                    wr(mem,0xE7E,2,q);wr(mem,0xE7C,2,0)
                    wr(r.reg,16,2,data-3);r.reg[1]=n
                    call(r,0xEF3A)
                    assert rd(r.reg,0,2)==stored_q8(mem,data,v),(m['id'],v,'lookup')
                    count += 1
    return count


def caller_cases(r):
    rng = random.Random(660)
    count = 0
    for synthetic in (False,True):
        for branch in range(3):
            for n in range(160):
                m = reset(r)
                if synthetic:
                    for data,(axis,size) in STORED.items():
                        m[data:data+size] = bytes(rng.randrange(256) for _ in range(size))
                for address in (0x900,0x920,0x910,0x912,0x90C,0x966):
                    wr(m,address,2,rng.randrange(65536))
                m[0x914],m[0x915] = rng.randrange(256),rng.randrange(256)
                m[0x88F] = 128 if branch==0 else 0
                m[0x89A] = m[0x355F] if branch==1 else min(255,m[0x355F]+1)
                response = (0x3570,0x3578,0x3580)[branch]
                p = uniform(m,0x35E0,2,rd(m,0x900,2))
                c = uniform(m,0x35A3,1,m[0x914])
                t = uniform(m,0x35C3,1,m[0x915])
                gain = min(65535,p*c*(t+384)//256)
                for data,address in ((0x35FE,0x920),(0x3618,0x910)):
                    gain = min(65535,gain*stored(m,data,rd(m,address,2))//256)
                pulse = min(25000,gain*stored(m,response,rd(m,0x912,2))*stored(m,0x359A,rd(m,0x90C,2))//4096)
                duration = min(65535,pulse+rd(m,0x966,2))
                r.run((0xE238,0xE387))
                assert (rd(m,0xA1E,2),rd(m,0xA1C,2),m[0xA27]&8)==(pulse,duration,8),(branch,n)
                count += 1
    # Caller entry conditions: port inhibit, crank phase, captured pair available.
    for port in (0,32):
        for phase in (0,1):
            for captured in (0,16):
                m = reset(r);m[0x20]=port;m[0x942]=m[0x355E]^phase;m[0xA27]=captured
                wr(m,0xA1E,2,54321);wr(m,0xA1C,2,54322)
                r.run((0xE21D,0xE387))
                entered = port==0 and phase==0 and captured!=0
                assert bool(m[0xA27]&8)==entered
                if not entered: assert (rd(m,0xA1E,2),rd(m,0xA1C,2))==(54321,54322)
                count += 1
    return count


def build():
    code = load_code('late');results=[]
    registry = {e['id']:e for e in json.loads((ROOT/'firmware/registry.json').read_text(encoding='utf-8'))['images']}
    for item in json.loads((ROOT/'analysis/firmware/decode_catalog.json').read_text(encoding='utf-8'))['images']:
        if item['family']!='late': continue
        e=registry[item['id']];raw=(ROOT/e['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==e['sha256']
        r=Replay(b'\xff'*e['base_address']+raw,code)
        maps=json.loads((ROOT/item['maps_path']).read_text(encoding='utf-8'))
        selected=[m for m in maps if int(m['data_address'],16) in STORED.keys()|UNIFORM.keys()]
        assert len(selected)==9
        helpers=helper_cases(r,selected);callers=caller_cases(r)
        results.append(dict(id=item['id'],firmware_sha256=e['sha256'],maps=[m['id'] for m in selected],
            helper_cases=helpers,caller_cases=callers,instructions_byte_checked=len(r.executed),
            stored_config={hex(a):r.image[a] for a in (0x1846,0x1847,0x1848,0x1849,0x3552,0x3553)}))
        print(item['id'],helpers,callers,flush=True)
    return dict(result='passed',cases=sum(r['helper_cases']+r['caller_cases'] for r in results),images=results,
        test_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        dependencies={n:hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest() for n in ('test_speed_sources.py','test_full_lift.py','test_firmware_lookups.py')},
        scope='Actual EE81/EF7F/EFA4/EF3A helpers, clamps, fractional lookup, three selections, E21D entry gates and E238..E383 pulse arithmetic. Synthetic RAM/calibration; no physical units, full ADC lifecycle, output edge timing or hardware validation.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args();result=build()
    if args.check: assert json.loads(REPORT.read_text(encoding='utf-8'))==result,'stale later transient evidence'
    else: REPORT.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Later transient audit:',result['cases'],'checks passed')
