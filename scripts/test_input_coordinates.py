"""Replay TPS, transient-delta and supply coordinates in every registered BIN.

Independent arithmetic/branch models versus byte-checked CPU12 instructions.
Synthetic RAM/calibration fixtures do not modify the source images. Counts and
task intervals are established here; electrical and mechanical scales are not.
"""
import argparse
import hashlib
import json
import random
from pathlib import Path

from test_firmware_lookups import load_code, rd, wr
from test_speed_sources import Replay

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'analysis/firmware/input_coordinate_validation.json'
LAYOUTS = {
    'early': dict(source=(0x6A68,0x6A9B), adc=0x8CA, raw=0x8D0, relative=0x8E2,
        published=0x8CE, fault=0x8AF, fallback=0x4E60, baseline=0x8E0,
        learn=(0x8C3C,0x8C74), learn_count=0x8EF, filtered=0x8E6,
        filter=(0x8C74,0x8CBE), latched=0x8E4, filter_gain=0x1840,
        history=(0x8EA2,0x8F1B), ring=0xB0E, index=0xB0D, mask=0x1842,
        delta=0x8ED, hold=0xB03, hold_threshold=0x19D7, steady=0xB17, steady_threshold=0x348B,
        axis=(0x7800,0x7833), fuel_axis=0x8E8, axis_gain=0x1841, axis_hold=0x19D8,
        load=(0x7833,0x78BC), load_source=0xC8C, load_filter=0x8F0, load_raw=0x988,
        load_delta=0x989, load_magnitude=0xDDF, load_gain=(0x3343,0x3342), load_deadband=0x3344,
        transient=(0x793D,0x7A2F), tfilter=0x8EA, tgain=(0x3339,0x333A),
        tconfig=0x333B, tcount=0xB02, thold=0xB04, traw=0x984, tdelta=0x985, tmag=0xDE2,
        stale=0xAFE, supply=(0x9EEE,0x9F19), supply_raw=0x8D9, supply_filtered=0x8DA,
        supply_gain=0x18B2, supply_fault=(0x6EBB,0x6ECA), supply_fault_flags=0x8B1, supply_adc=0xBCE),
    'late': dict(source=(0x62C7,0x62FA), adc=0x8D0, raw=0x8D6, relative=0x8EC,
        published=0x8D4, fault=0x8B1, fallback=0x45FC, baseline=0x8EA,
        learn=(0x8034,0x80B5), learn_count=0x8FC, filtered=0x8F0,
        filter=(0x80B5,0x80FF), latched=0x8EE, filter_gain=0x1843,
        history=(0x82DC,0x834C), ring=0xB46, index=0xB45, mask=0x1845,
        delta=0x8FA, extended_delta=0x8F8, hold=0xB36, hold_threshold=0x19B1, steady=0xB4F, steady_threshold=0x3452,
        axis=(0x6FFD,0x7030), fuel_axis=0x8F2, axis_gain=0x1844, axis_hold=0x19B2,
        load=(0x7030,0x70B2), load_source=0xCAE, load_filter=0x8FE, load_raw=0x986,
        load_delta=0x987, load_magnitude=0xE63, load_gain=(0x330B,0x330A), load_deadband=0x330C,
        transient=(0x7128,0x7213), tfilter=0x8F4, tgain=(0x3301,0x3302),
        tconfig=0x3303, tcount=0xB35, thold=0xB37, traw=0x982, tdelta=0x983, tmag=0xE66,
        stale=0xB31, supply=(0x9371,0x939C), supply_raw=0x8DF, supply_filtered=0x8E0,
        supply_gain=0x188C, supply_fault=(0x6770,0x677F), supply_fault_flags=0x8B3, supply_adc=0xBF0),
}


def clamp(n, low=0, high=65535):
    return min(high, max(low, n))


def track(previous, target, gain):
    step = abs(target-previous)*gain//256
    return previous+step if target>=previous else previous-step


def reset(r):
    r.ram[:] = bytes(0x1800)+r.image[0x1800:]
    r.reg[:] = bytes(64)
    return r.ram


def neutral(m, early, value):
    if early:
        m[0xD87],m[0x896] = 9,0 if value else 16
    else:
        m[0x88F] = 128 if value else 0


def sensor_cases(r,l,rng):
    for n in range(4096):
        m=reset(r);adc=n%1024;flags=(0,4,8,12)[n//1024];relative=rng.randrange(1024)
        wr(m,l['adc'],2,adc*64);wr(m,l['relative'],2,relative);m[l['fault']]=flags
        fallback=rd(m,l['fallback'],2)
        r.run(l['source'])
        assert rd(m,l['raw'],2)==(fallback if flags else adc)
        assert rd(m,l['published'],2)==((fallback if flags else relative)*64)&65535
    return 4096


def learning_cases(r,l,early,rng):
    for n in range(768):
        m=reset(r)
        raw,base=rng.randrange(1024),rng.randrange(1024)
        count=(0,1,2,3,4,254,255)[n%7]
        wr(m,l['raw'],2,raw);wr(m,l['baseline'],2,base);m[l['learn_count']]=count
        if early:
            count=min(255,count+1) if raw<base else 0
            if count>=4:base=max(0,base-1);count=0
        else:
            quality=(0,127,128,129,65535)[n%5]
            limit=(0,128,129,256,65535)[(n//5)%5]
            elapsed=(0,1,254,255)[(n//25)%4];minimum=n%256;floor=rng.randrange(1024)
            wr(m,0x8E6,2,quality);wr(m,0x4442,2,limit);m[0xB2C]=elapsed;m[0x4444]=minimum;wr(m,0x4446,2,floor)
            qualified=abs(quality-128)<max(0,limit-128)
            if qualified and elapsed>=minimum and raw<base:
                count=min(255,count+1)
                if count>=4:base=max(floor,max(0,base-1));count=0
            else:count=0
            expected_elapsed=min(255,elapsed+1) if qualified else 0
        r.run(l['learn'])
        assert rd(m,l['baseline'],2)==base and m[l['learn_count']]==count,(early,n)
        assert rd(m,l['relative'],2)==max(0,raw-base)
        if not early:assert m[0xB2C]==expected_elapsed
    return 768


def filter_cases(r,l,rng):
    for n in range(1024):
        m=reset(r);target,previous,latched=[rng.randrange(1024) for _ in range(3)];gain=n%256
        if n<32:target,latched=512,512+(n-16)
        flags=rng.randrange(256)
        for a,v in [(l['relative'],target),(l['filtered'],previous),(l['latched'],latched)]:wr(m,a,2,v)
        m[l['filter_gain']],m[0x88D]=gain,flags
        changed=abs(latched-target)>=8
        r.run(l['filter'])
        assert rd(m,l['filtered'],2)==track(previous,target,gain)
        assert rd(m,l['latched'],2)==(target if changed else latched)
        assert m[0x88D]==(flags|12 if changed else flags&~8)
    return 1024


def history_cases(r,l,early,rng):
    cases=0
    for mask in (0,1,3,7):
        m=reset(r);m[l['mask']]=mask;index=0;history=[rng.randrange(1024) for _ in range(4)]
        for k,v in enumerate(history):wr(m,l['ring']+2*k,2,v)
        for n in range(1024):
            value=n if n%3 else 1023-n
            old=history[index//2];encoded=clamp(128+value-old,0,255)
            extended=clamp(128+value-old,0,1151)
            hold,steady,start=rng.randrange(256),rng.randrange(256),bool(n%2)
            m[l['hold']],m[l['steady']],m[0x881]=hold,steady,16 if start else 0
            wr(m,l['filtered'],2,value)
            r.run(l['history'])
            assert m[l['delta']]==encoded,(early,n,value,old)
            if not early:assert rd(m,l['extended_delta'],2)==extended
            assert m[l['hold']]==(255 if start else 0 if encoded>=m[l['hold_threshold']] else hold)
            assert m[l['steady']]==(min(255,steady+1) if encoded<=m[l['steady_threshold']] else 0)
            history[index//2]=value
            assert rd(m,l['ring']+index,2)==value
            index=(index+2)&mask
            assert m[l['index']]==index
            cases+=1
    return cases


def axis_cases(r,l,rng):
    for n in range(1024):
        m=reset(r);source,previous=[rng.randrange(65536) for _ in range(2)];gain=n%256
        hold,limit=(n//256,2)
        wr(m,l['published'],2,source);wr(m,l['fuel_axis'],2,previous)
        m[l['axis_gain']],m[l['hold']],m[l['axis_hold']]=gain,hold,limit
        r.run(l['axis'])
        assert rd(m,l['fuel_axis'],2)==(source if hold<limit else track(previous,source,gain))
    return 1024


def load_delta_cases(r,l,early,rng):
    for n in range(2048):
        m=reset(r);source,previous=[rng.randrange(65536) for _ in range(2)];gain=n%256
        is_neutral=bool(n%2);neutral(m,early,is_neutral)
        stale=(0,99,100,255)[(n//2)%4];deadband=(0,1,126,127,128,255)[(n//8)%6]
        m[l['load_gain'][0 if is_neutral else 1]],m[l['stale']],m[l['load_deadband']]=gain,stale,deadband
        wr(m,l['load_source'],2,source);wr(m,l['load_filter'],2,previous)
        filtered=source if stale<100 else track(previous,source,gain)
        delta=(source>>8)-(filtered>>8);mag=min(127,abs(delta));code=128+(-mag if delta<0 else mag)
        r.run(l['load'])
        assert rd(m,l['load_filter'],2)==filtered
        assert m[l['load_raw']]==code
        assert m[l['load_delta']]==(128 if mag<=deadband else code)
        assert m[l['load_magnitude']]==(0 if mag<=deadband else mag)
    # Every attainable magnitude is below the supplied 255 deadband, in all BINs.
    assert r.image[l['load_deadband']]==255
    return 2048


def throttle_delta_cases(r,l,early,rng):
    for n in range(3072):
        m=reset(r);source,previous,axis=[rng.randrange(65536) for _ in range(3)]
        gain=n%256;is_neutral=bool(n%2);neutral(m,early,is_neutral)
        cfg=[rng.randrange(256) for _ in range(7)]
        # All stock constants participate as well as boundary/alternate fixtures.
        if n%3==0:cfg=list(r.image[l['tconfig']:l['tconfig']+7])
        m[l['tconfig']:l['tconfig']+7]=bytes(cfg)
        m[l['tgain'][0 if is_neutral else 1]]=gain
        count,hold,flags,history_delta,stale=[rng.randrange(256) for _ in range(5)]
        m[l['tcount']],m[l['thold']],m[0x885],m[l['delta']],m[l['stale']]=count,hold,flags,history_delta,stale
        wr(m,l['published'],2,source);wr(m,l['tfilter'],2,previous);wr(m,l['fuel_axis'],2,axis)
        filtered=track(previous,source,gain);adjust=False
        if count<=((cfg[4]-1)&255):
            if min(255,hold+1)<cfg[2]:hold=min(255,hold+1);flags|=2;adjust=True
        else:
            flags&=~2
            if axis>>8<=cfg[0] and history_delta>=cfg[1]:count=hold=0;flags|=2;adjust=True
        baseline=clamp((filtered>>8)-cfg[3],0,255) if adjust else filtered>>8
        delta=(axis>>8)-baseline;mag=min(127,abs(delta));code=128+(-mag if delta<0 else mag)
        if axis>>8>=cfg[5] or stale<100:mag=0;code=128
        filtered_code=128 if mag<=cfg[6] else code
        filtered_mag=0 if mag<=cfg[6] else mag
        r.run(l['transient'])
        assert rd(m,l['tfilter'],2)==filtered
        assert (m[l['tcount']],m[l['thold']],m[0x885])==(count,hold,flags),(early,n)
        assert (m[l['traw']],m[l['tdelta']],m[l['tmag']])==(code,filtered_code,filtered_mag),(early,n)
    return 3072


def supply_cases(r,l,rng):
    for n in range(1024):
        m=reset(r);raw=n%256;fault=bool((n//256)%2)
        m[l['supply_adc']],m[l['supply_fault_flags']]=raw,4 if fault else 0
        r.run(l['supply_fault']);effective=154 if fault else raw
        assert m[l['supply_raw']]==effective
        previous=rng.randrange(65536);gain=n%256;start=bool(n//512)
        wr(m,l['supply_filtered'],2,previous);m[l['supply_gain']]=gain;m[0x881]=16 if start else 0
        r.run(l['supply'])
        assert rd(m,l['supply_filtered'],2)==(effective*256 if start else track(previous,effective*256,gain))
    return 1024


def build():
    codes={f:load_code(f) for f in LAYOUTS};results=[]
    for entry in json.loads((ROOT/'analysis/firmware/catalog.json').read_text())['images']:
        raw=(ROOT/entry['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==entry['sha256']
        image=b'\xff'*entry['base_address']+raw;family=entry['code_family'];early=family=='early'
        r=Replay(image,codes[family]);l=LAYOUTS[family];rng=random.Random(660051)
        checks={}
        for name,fn,args in [('adc_and_fault_source',sensor_cases,(r,l,rng)),('learned_baseline',learning_cases,(r,l,early,rng)),
                            ('relative_filter_and_movement_latch',filter_cases,(r,l,rng)),('history_delta',history_cases,(r,l,early,rng)),
                            ('fuel_axis_filter_and_hold',axis_cases,(r,l,rng)),('load_delta_deadband',load_delta_cases,(r,l,early,rng)),
                            ('throttle_delta_qualification',throttle_delta_cases,(r,l,early,rng)),('supply_filter_and_fault',supply_cases,(r,l,rng))]:
            checks[name]=fn(*args)
        results.append(dict(id=entry['id'],firmware_sha256=entry['sha256'],family=family,checks=checks,
                            stock_load_delta_deadband=image[l['load_deadband']],stock_history_mask=image[l['mask']],
                            executed_instructions=len(r.executed),instruction_addresses=[f'0x{a:04X}' for a in sorted(r.executed)]))
        print(entry['id'],sum(checks.values()),'passed',flush=True)
    return dict(result='passed',cases=sum(sum(r['checks'].values()) for r in results),images=results,
                test_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                dependencies={n:hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest() for n in ['test_speed_sources.py','test_firmware_lookups.py','test_full_lift.py']},
                limits=['Instruction replay, not a live ECU/interrupt timing test','No sensor voltage/angle/temperature transfer is inferred','Task period in physical time remains conditional on clock'])


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
    result=build()
    if args.check:assert json.loads(REPORT.read_text())==result,'Input coordinate report is stale'
    else:REPORT.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Input coordinates:',result['cases'],'cases passed')
