"""Independent waveform checks and crank streams through unchanged firmware."""
import re
from crank import crank, events
from runner import execute, prepare, registered_image, RUNS
from test_peripherals import Checks


def test_bit_branches(executable,wsl):
    c=Checks()
    for op,operand,address in [(0x4e,[0x20],0x20),(0x1e,[0x12,0],0x1200),(0x0e,[0],0x1200)]:
        for clear in (False,True):
            for value,mask in [(0x81,0x81),(1,0x81),(0,0x81),(255,0),(0,0)]:
                taken=(value&mask)==(0 if clear else mask)
                code=[op+clear]+operand+[mask,5]
                c.commands.append(f'reset\nCC=0xd3\nIX=0x1200\nset memory rom {address} {value}\n')
                c.code(code,1)
                c.check(f'bit branch {op+clear:02x} {value}/{mask}',f'(PC=={0x1000+len(code)+(5 if taken else 0)})&&(CC==0xd3)')
    checks=c.run(executable,wsl,'bit-branches.log')
    script='reset\nset memory rom 0x1000 0x1e 0x12 0 0x81 5\ndc 0x1000 0x1000\n'
    script+='set memory rom 0x1000 0x4f 0x20 0x80 0xfc\ndc 0x1000 0x1000\n'
    script+='set memory rom 0x1000 0x0c 0xe2 1 0 0x42\ndc 0x1000 0x1000\n'
    script+='set memory rom 0x1000 0x0e 0xe2 1 0 0x42 5\ndc 0x1000 0x1000\n'
    script+='set memory rom 0x1000 0x0f 0xe0 0x20 0x42 0xf9\ndc 0x1000 0x1000\n'
    script+='set memory rom 0x1000 0x0d 0x20 0x42\ndc 0x1000 0x1000\n'
    script+='set memory rom 0x1000 0x0c 0xe3 0x12 0 0x43\ndc 0x1000 0x1000\n'
    script+='set memory rom 0x1000 0x0e 0xe4 0x44 5\ndc 0x1000 0x1000\nquit\n'
    out=execute(executable,script,wsl)
    (RUNS/'bit-disassembly.log').write_text(out,encoding='utf-8')
    assert re.search(r'BRSET\s+\$1200,#\$81,\$100a',out,re.I),out
    assert re.search(r'BRCLR\s+\$0020,#\$80,\$1000',out,re.I),out
    assert re.search(r'BSET\s+.*#\$42',out,re.I),out
    assert re.search(r'BRSET\s+.*#\$42,\$100b',out,re.I),out
    assert re.search(r'BRCLR\s+.*#\$42,\$0ffe',out,re.I),out
    assert re.search(r'BCLR\s+.*#\$42',out,re.I),out
    assert re.search(r'BSET\s+.*#\$43',out,re.I),out
    assert re.search(r'BRSET\s+.*#\$44,\$1009',out,re.I),out
    return dict(execution=checks,disassembly=8)


def test_pulse_fixture(executable,wsl):
    checks=0
    for gap in (0,3):
        script='reset\nCC=0xd0\nfill rom 0x1000 0x17ff 0xa7\npc 0x1000\n'
        script+='set memory rom 0x44 0xff 0xf0\nset memory rom 0x46 128\nset memory rom 0x4b 8\n'
        for a,v in [(19,64),(20,16),(21,gap),(22,2),(23,6),(25,1),(24,1)]:
            script+=f'set memory xtboot_0_cfg {a} {v}\n'
        script+='step 600\ninfo hardware xtboot\nquit\n'
        out=execute(executable,script,wsl)
        trace=events(out)
        falling=[e for e in trace if e['kind']=='input' and e['value']==0]
        captures=[e for e in trace if e['kind']=='capture']
        expected=[];time=0
        for n in range(1,7):
            time+=128 if gap and n%gap==0 else 64
            expected.append(time)
        assert [e['cycle'] for e in falling]==expected,(gap,trace)
        assert [e['cycle'] for e in captures]==expected,(gap,trace)
        assert [e['value'] for e in captures]==[(0xfff0+x)&65535 for x in expected]
        rises=[e['cycle'] for e in trace if e['kind']=='input' and e['value']==1]
        assert rises==[0]+[x+16 for x in expected]
        assert 'PULSES=6 PULSE_RUNNING=0' in out and 'FAULT=0' in out
        checks+=5
    # The timer output trace must record the hardware compare, not an ISR store.
    out=execute(executable,'reset\nCC=0xd0\nfill rom 0x1000 0x17ff 0xa7\npc 0x1000\n'
                'set memory rom 0x40 8\nset memory rom 0x49 0xc0\nset memory rom 0x56 0 40\n'
                'set memory rom 0x46 128\nset memory xtboot_0_cfg 25 1\nstep 50\nquit\n',wsl)
    edges=[e for e in events(out) if e['kind']=='output']
    assert [(e['cycle'],e['channel'],e['value']) for e in edges]==[(40,3,1)],edges
    out=execute(executable,'reset\nset memory xtboot_0_cfg 20 51200\n'
                'set memory xtboot_0_cfg 24 1\ninfo hardware xtboot\nquit\n',wsl)
    assert 'invalid PT1 pulse fixture' in out and 'PULSES=0 PULSE_RUNNING=0' in out
    return checks+2


def test_crank(executable,wsl):
    images=['xt660-2004-2006-companion','xt660-5vk-1x-2008','xt660-2c1-10',
            'xt660-2c1-10-immo-off','xt660-5vk-11']
    cases=[(i,1600,False) for i in images]
    cases += [(images[0],p,False) for p in (800,2400)]
    cases += [(i,1600,True) for i in (images[0],images[3])]
    results=[]
    for image,pitch,uniform in cases:
        report,trace=crank(executable,image,wsl,pitch=pitch,uniform=uniform)
        assert report['completed'],report
        assert report['falling_edges']==report['captures']==132,report
        falling=[e for e in trace if e['kind']=='input' and e['value']==0]
        captures=[e for e in trace if e['kind']=='capture' and e['channel']==1]
        for n in range(1,len(falling)):
            expected=pitch*(2 if not uniform and (n+1)%11==0 else 1)
            assert falling[n]['cycle']-falling[n-1]['cycle']==expected*32
            assert (captures[n]['value']-captures[n-1]['value'])&65535==expected
        assert report['running']['synchronized']==(not uniform),report
        if not uniform:
            assert report['running']['pitch_ticks']==pitch,report
            assert report['running']['three_pitch_ticks']==3*pitch,report
            assert report['running']['phase']==0,report
        assert not report['after_pulse_loss']['synchronized'],report
        assert report['after_pulse_loss']['pitch_ticks']==65535,report
        if image==images[3] and not uniform:
            spark=report['ignition_edges']
            assert len(spark)>=12 and [e['level'] for e in spark]==[1,0]*(len(spark)//2)
            falling_times=[e['cycle'] for e in spark if e['level']==0]
            # Fixed-event path: ISR latency varies, so one-pattern cadence has a
            # small instruction-boundary tolerance, not invented exact BTDC.
            assert all(abs(b-a-12*pitch*32)<=128 for a,b in zip(falling_times,falling_times[1:]))
        report.pop('trace');report.pop('event_csv')
        results.append(report)
    return results


def test_output_gates(executable,wsl):
    results=[]
    for image,loop,gate,target,flag,mask in [
        ('xt660-2004-2006-companion',0x538b,0xee2d,0xee77,0xd08,1),
        ('xt660-2c1-10-immo-off',0x4bc5,0xf256,0xf260,0x8b3,16)]:
        record,setup=prepare(image,wsl)
        _,data=registered_image(image);mem=bytes(record['base_address'])+data
        expected=bytes([0x1e,flag>>8,flag&255,mask,(target-gate-5)&255])
        assert mem[gate:gate+5]==expected
        command=setup+'set memory xtboot_0_cfg 9 224\nset memory xtboot_0_cfg 13 16\n'
        command+=f'break {loop} 1000\nstep 2000000\ndelete\nset memory xtboot_0_cfg 24 1\n'
        command+=f'break {gate} 1 if "(rom[{flag}]&{mask})!=0"\nstep 10000000\nstep\ninfo hardware xtboot\nquit\n'
        out=execute(executable,command,wsl,timeout=120)
        (RUNS/f'{image}-output-gate.log').write_text(out,encoding='utf-8')
        stops=[(int(a,16),int(c)) for a,c in re.findall(r'Stop at 0x([0-9a-fA-F]+): \((\d+)\)',out)]
        assert stops==[(loop,104),(gate,104),(target,109)],(image,stops)
        assert 'FAULT=0' in out and 'unmodelled' not in out
        results.append(dict(image=image,instruction=f'0x{gate:04X}',bytes=expected.hex(),
                            flag=f'0x{flag:04X}',mask=mask,return_path=f'0x{target:04X}'))
    return results
