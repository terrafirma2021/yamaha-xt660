"""Independent HC12 fixtures, debugger checks and real-BIN startup checks."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from runner import ROOT, RUNS, execute, prepare, registered_image
from test_runtime_devices import test_timer_spi, test_watchdog, test_runtime, test_runtime_guards
from test_crank import test_bit_branches, test_pulse_fixture, test_crank, test_output_gates
from test_peripherals import test_peripherals, test_interrupts, test_firmware_adc, test_sensor_demo


def core_cases():
    cases = []

    def add(name, code, setup, expect, steps=1):
        command = 'set memory rom 0x1000 ' + ' '.join(f'0x{b:02x}' for b in code) + '\n'
        command += setup + '\npc 0x1000\n' + f'step {steps}\n'
        cases.append((name, command, expect))

    # High-byte loss, byte borrow, word wrap, Z and preserved flags.
    for reg, op, other in [('IX', 9, 'IY'), ('IY', 3, 'IX')]:
        for high in range(0, 256, 7):
            for low in (0, 1, 2, 255):
                value = high * 256 + low
                result = (value - 1) & 65535
                cc = 0xd3 | (4 if result == 0 else 0)
                add(f'{reg} decrement {value:04x}', [op],
                    f'{reg}={value}\n{other}=0x55aa\nCC=0xd7',
                    f'({reg}=={result})&&({other}==0x55aa)&&(CC=={cc})&&(PC==0x1001)')

    # All loop primitive types, both branch predicates, 8/16-bit registers.
    for reg, selector, width in [('A',0,8),('B',1,8),('D',4,16),('IX',5,16),('IY',6,16),('SP',7,16)]:
        for kind, delta in [(0,-1),(0x40,0),(0x80,1)]:
            for ne in (0, 0x20):
                for value in (0, 1, 2, (1<<width)-1):
                    result = (value + delta) & ((1<<width)-1)
                    taken = (result != 0) if ne else (result == 0)
                    add(f'loop {kind:02x}/{ne:02x} {reg}={value}', [4,kind|ne|selector,5],
                        f'{reg}={value}\nCC=0xd3',
                        f'({reg}=={result})&&(PC=={0x1008 if taken else 0x1003})&&(CC==0xd3)')

    # Auto-indexing address and register update are checked independently.
    for reg, bits in [('IX',0),('IY',0x40),('SP',0x80)]:
        for post in (False, True):
            for delta in (-8,-2,-1,1,2,8):
                nibble = delta & 15 if delta < 0 else delta-1
                xb = bits | 0x20 | (0x10 if post else 0) | nibble
                ea = 0x1400 if post else 0x1400+delta
                add(f'auto-index {reg} post={post} delta={delta}', [0xe6,xb],
                    f'IX=0x1400\nIY=0x1400\nSP=0x1400\nset memory rom {ea} 0xa6',
                    f'(B==0xa6)&&({reg}=={0x1400+delta})&&(PC==0x1002)')

    # Distinct X,Y,SP values catch swapped register selection in larger offsets.
    for reg, bits, base in [('IX',0,0x1200),('IY',8,0x1400),('SP',16,0x1600)]:
        for offset in (-128, 0, 127, 256):
            xb = 0xe0 | bits | (1 if offset < 0 else 0)
            operand = [xb, offset&255] if offset < 256 else [0xe2|bits,1,0]
            add(f'offset {reg} {offset}', [0xe6]+operand,
                f'IX=0x1200\nIY=0x1400\nSP=0x1600\nset memory rom {base+offset} 0xa6',
                f'(B==0xa6)&&(IX==0x1200)&&(IY==0x1400)&&(SP==0x1600)')
        for use_d in (False, True):
            code = [0xe6,0xe7|bits] if use_d else [0xe6,0xe3|bits,0,4]
            add(f'indirect {reg} use_D={use_d}', code,
                f'IX=0x1200\nIY=0x1400\nSP=0x1600\nD=4\n'
                f'set memory rom {base+4} 0x11 0x00\nset memory rom 0x1100 0xa6',
                '(B==0xa6)&&(IX==0x1200)&&(IY==0x1400)&&(SP==0x1600)')

    # Sequencing two instruction-stream fetches must not depend on C++ compiler order.
    for op, operand, address in [(0x4c,[0x20],0x20),(0x1c,[0x12,0],0x1200),(0x0c,[0],0x1200)]:
        for clear in (False, True):
            for original, mask in [(0x42,0x81),(0xff,0x55),(0,0xff),(0x80,0)]:
                value = original & (~mask&255) if clear else original | mask
                add(f'bit operation {op+clear:02x} {original:02x}/{mask:02x}',
                    [op+clear]+operand+[mask],
                    f'IX=0x1200\nset memory rom {address} {original}',
                    f'(rom[{address}]=={value})&&(PC=={0x1002+len(operand)})')
    return cases


def test_core(executable, wsl):
    cases = core_cases()
    commands = []
    for index, (_, setup, expect) in enumerate(cases):
        commands.append(setup + f'expression /X (0x66000000+{index*2}+({expect}))\n')
    output = execute(executable, ''.join(commands)+'quit\n', wsl, timeout=60)
    values = [int(v,16) for v in re.findall(r'(?m)^0x(66[0-9a-fA-F]{6})\s*$', output)]
    RUNS.mkdir(exist_ok=True)
    (RUNS/'core.log').write_text(output)
    if len(values) != len(cases):
        raise AssertionError(f'Expected {len(cases)} fixture results; received {len(values)}; see core.log')
    failures = [name for i, ((name,_,_),value) in enumerate(zip(cases,values))
                if value != 0x66000000+i*2+1]
    assert not failures, failures[:15]
    assert 'Parser error' not in output and 'XT660 unmodelled' not in output
    return len(cases)


def test_boot(executable, wsl):
    rows = json.loads((ROOT/'firmware/registry.json').read_text())['images']
    result = []
    for row in rows:
        try:
            record, setup = prepare(row['id'], wsl)
        except ValueError as error:
            assert 'Boot code is absent' in str(error), error
            result.append({'image': row['id'], 'status': 'boot_absent_rejected'})
            continue
        _, data = registered_image(row['id'])
        # Breakpoint hit counts demonstrate that both actual wait loops execute.
        ram_check = '&&'.join(f'(rom[{a}]==0)' for a in range(0x800,0x1000))
        output = execute(executable, setup+'fill rom 0x800 0xfff 0xa5\n'
                         'break 0xf816 2\nstep 200000\ndelete\n'
                         'break 0xf859 2\nstep 200000\ndelete\n'
                         f'break 0x{record["application_entry"]:04x}\nstep 200000\n'
                         f'expression /X (0x66000000+({ram_check}))\n'
                         'info hardware xtboot\n'
                         'dump /i rom 0x1800 0xffff 16\nquit\n', wsl)
        (RUNS/(row['id']+'.log')).write_text(output)
        stops = re.findall(r'Stop at 0x([0-9a-fA-F]+): \((\d+)\)', output)
        assert [(int(a,16),int(code)) for a,code in stops] == [(0xf816,104),(0xf859,104),(record['application_entry'],104)], (row['id'],stops)
        assert re.search(r'(?m)^0x66000001\s*$',output), row['id']+' RAM not cleared'
        assert 'FAULT=0' in output and 'XT660 unmodelled' not in output
        # Intel HEX dump independently checks EVERY firmware byte after execution.
        memory = {}
        for match in re.finditer(r'(?m)^:([0-9a-fA-F]+)\s*$',output):
            line = bytes.fromhex(match[1])
            assert sum(line)%256==0
            if line[3] == 0:
                address = int.from_bytes(line[1:3],'big')
                memory.update({address+i:b for i,b in enumerate(line[4:-1])})
        assert len(memory)==0xe800, (row['id'],len(memory))
        assert bytes(memory[a] for a in range(0x1800,0x10000)) == data[0x1800-record['base_address']:]
        result.append({'image':row['id'], 'status':'application_entry_reached',
                       'application_entry':f'0x{record["application_entry"]:04x}',
                       'flash_bytes_unchanged':0xe800, 'ram_clear_bytes':0x800})
    return result


def test_debugger_and_device(executable, wsl):
    launch = [sys.executable, str(ROOT/'emulator/run.py'), '--ucsim', str(executable), '--console']
    if wsl:
        launch.append('--wsl')
    console = subprocess.run(launch, input='info registers\nquit\n', text=True,
                             capture_output=True, timeout=30, check=True)
    assert '0xf800' in console.stdout and 'Breakpoint 1 at 0x005000' in console.stdout
    (RUNS/'console.log').write_text(console.stdout+console.stderr)
    # Conditional execution stop, write watchpoint, read watchpoint, step over JSR.
    script = '''set memory rom 0x1000 0x86 0x02 0x7a 0x12 0x00 0xb6 0x12 0x00
set memory rom 0x1200 0x00
pc 0x1000
break 0x1002 if A==2
step 20
expression /X 0x66000000+((PC==0x1002)&&(rom[0x1200]==0))
delete
break rom w 0x1200
step 20
expression /X 0x66000002+((PC==0x1005)&&(rom[0x1200]==2))
delete
break rom r 0x1200
step 20
expression /X 0x66000004+((PC==0x1008)&&(A==2))
delete
set memory rom 0x1000 0x16 0x11 0x00 0xa7
set memory rom 0x1100 0x86 0x42 0x3d
SP=0x0ff0
pc 0x1000
next
expression /X 0x66000006+((PC==0x1003)&&(A==0x42)&&(SP==0x0ff0))
quit
'''
    output = execute(executable, script, wsl)
    (RUNS/'debugger.log').write_text(output)
    values = re.findall(r'(?m)^0x(66[0-9a-fA-F]{6})\s*$',output)
    assert [int(v,16) for v in values] == [0x66000001,0x66000003,0x66000005,0x66000007], values

    # BSET on a W1C flag clears it; unknown IO and direct CPU flash stores stop.
    script = '''set memory rom 0x67 0x80
set memory rom 0x1000 0x4c 0x67 0x80
pc 0x1000
step
expression /X 0x66000000+((rom[0x67]&0x80)==0)
set memory rom 0x1000 0x96 0x80 0xa7
pc 0x1000
step 10
info hardware xtboot
reset
set memory rom 0x1000 0x86 0x77 0x7a 0x20 0x00 0xa7
set memory rom 0x2000 0xaa
pc 0x1000
step 10
expression /X 0x66000002+(rom[0x2000]==0xaa)
info hardware xtboot
quit
'''
    output = execute(executable, script, wsl)
    (RUNS/'device-guards.log').write_text(output)
    values = re.findall(r'(?m)^0x(66[0-9a-fA-F]{6})\s*$',output)
    assert [int(v,16) for v in values] == [0x66000001,0x66000003], values
    assert 'unmodelled read at register 0080' in output
    assert 'unmodelled CPU flash write at register 2000' in output
    assert output.count('FAULT=1') == 2

    # FLMC reload, simulated clock progress, one-shot expiry, and W1C.
    script = '''set memory rom 0x1000 0xcc 0x01 0x00 0x5c 0x76 0x86 0x04 0x5a 0x66 0x4c 0x66 0x08 0xa7
pc 0x1000
step 5
info hardware xtboot
step
info hardware xtboot
fill rom 0x1100 0x11ff 0xa7
pc 0x1100
step 251
info hardware xtboot
set memory rom 0x1000 0x4c 0x67 0x80
pc 0x1000
step
info hardware xtboot
quit
'''
    output = execute(executable,script,wsl)
    (RUNS/'timer.log').write_text(output)
    states = re.findall(r'MCCNT=(\d+) MC_LOAD=(\d+) MCZF=(\d+) FAULT=(\d+)',output)
    assert states == [('252','256','0','0'),('251','256','0','0'),('0','256','1','0'),('0','256','0','0')], states
    return ['interactive console initialization', 'conditional breakpoint', 'write watchpoint', 'read watchpoint', 'JSR step over',
            'W1C flag', 'unknown IO stop', 'CPU flash write blocked',
            'timer reload/countdown/expiry/clear']


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ucsim',required=True)
    ap.add_argument('--wsl',action='store_true')
    ap.add_argument('--core-only',action='store_true')
    args=ap.parse_args()
    report={'core_fixtures':test_core(args.ucsim,args.wsl)}
    if not args.core_only:
        report['debugger_and_device']=test_debugger_and_device(args.ucsim,args.wsl)
        report['images']=test_boot(args.ucsim,args.wsl)
        report['peripheral_checks']=test_peripherals(args.ucsim,args.wsl)
        report['interrupt_checks']=test_interrupts(args.ucsim,args.wsl)
        report['firmware_adc']=test_firmware_adc(args.ucsim,args.wsl)
        report['sensor_demo']=test_sensor_demo(args.ucsim,args.wsl)
        report['timer_spi_checks']=test_timer_spi(args.ucsim,args.wsl)
        report['watchdog_checks']=test_watchdog(args.ucsim,args.wsl)
        report['runtime_guards']=test_runtime_guards(args.ucsim,args.wsl)
        report['runtime']=test_runtime(args.ucsim,args.wsl)
        report['bit_branches']=test_bit_branches(args.ucsim,args.wsl)
        report['pulse_fixture_checks']=test_pulse_fixture(args.ucsim,args.wsl)
        report['crank']=test_crank(args.ucsim,args.wsl)
        report['output_gate_checks']=test_output_gates(args.ucsim,args.wsl)
    report['ucsim_commit']='59a14ff99efe7e92474faf4c4ddf57b5e4ff0631'
    report['scope']='CPU/peripheral fixtures, main-loop runs and synthetic crank/capture/ignition/loss checks with disconnected SPI storage and idle serial; not full engine or physical ECU validation'
    report['source_hashes']={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted((ROOT/'emulator').rglob('*'))
                            if p.is_file() and not any(x.startswith('.') or x=='__pycache__' for x in p.relative_to(ROOT/'emulator').parts)
                            and p.suffix in ('.py','.cc','.patch')}
    (RUNS/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
