"""Drive synthetic PT1 edges through a running BIN; never seed ECU runtime RAM."""
import csv
import re
from runner import RUNS, execute, prepare, registered_image
from sensors import LATE_IMAGES


def hex_memory(text):
    result={}
    for match in re.finditer(r'(?m)^:([0-9a-fA-F]+)\s*$',text):
        block=bytes.fromhex(match[1])
        if len(block)!=block[0]+5 or sum(block)%256:
            raise RuntimeError('Invalid simulator HEX record')
        if block[3]==0:
            start=int.from_bytes(block[1:3],'big')
            result.update({start+n:v for n,v in enumerate(block[4:-1])})
    return result


def events(text):
    pattern=r'XT_EVENT cycle=(\d+) kind=(\w+) channel=(\d+) value=(\d+) pc=([0-9a-f]+)'
    return [dict(cycle=int(t),kind=k,channel=int(c),value=int(v),pc=f'0x{int(p,16):04X}')
            for t,k,c,v,p in re.findall(pattern,text)]


def crank(executable,image,wsl=False,pitch=1600,patterns=12,uniform=False,inputs=None,
          steps=10000000,loss=True,verify_flash=True):
    if not 400<=pitch<=4000 or not 4<=patterns<=24 or not 1<=steps<=10000000:
        raise ValueError('Crank bounds: pitch 400..4000 timer ticks, 4..24 patterns, 1..10000000 instructions.')
    inputs=[512]*8 if inputs is None else inputs
    if len(inputs)!=8 or any(type(x) is not int or not 0<=x<=1023 for x in inputs):
        raise ValueError('Supply eight ADC values in 0..1023.')
    record,setup=prepare(image,wsl)
    if image=='xt660-2004-2006-companion': late=False
    elif image in LATE_IMAGES: late=True
    else: raise ValueError('No reviewed crank profile for this image.')
    loop=0x4bc5 if late else 0x538b
    sync=0xc20 if late else 0xbfe
    phase=0xc26 if late else 0xc04
    pitch_ram=0xa38 if late else 0xa2e
    three_ram=0xa3e if late else 0xa34
    _,data=registered_image(image)
    memory=bytes(record['base_address'])+data
    # These setup instructions establish the /32 timer prescaler in both families.
    timer_setup=0x484c if late else 0x5057
    if memory[timer_setup:timer_setup+4]!=bytes.fromhex('c6055b4d'):
        raise ValueError('Startup timer divisor is outside the reviewed /32 profile')
    if memory[loop+8:loop+13]!=bytes.fromhex('ce0ffeb757'):
        raise ValueError('Main-loop entry bytes do not match this profile')
    commands=setup+'set memory xtboot_0_cfg 9 0xe0\nset memory xtboot_0_cfg 13 0x10\n'
    commands+=''.join(f'adc{n}={v}\n' for n,v in enumerate(inputs))
    commands+=f'break {loop} 1000\nstep 2000000\ndelete\n'
    for offset,value in [(19,pitch*32),(20,pitch*16),(21,0 if uniform else 11),(22,2),
                         (23,patterns*11),(25,1),(24,1)]:
        commands+=f'set memory xtboot_0_cfg {offset} {value}\n'
    commands+=f'break {loop} 1 if "xtboot_0_cfg[24]==0"\nstep {steps}\n'
    commands+='info hardware xtboot\nexpression /X 0x6600c001\ndump /i rom 0x800 0xfff 16\n'
    commands+='expression /X 0x6600c002\n'
    if loss:
        commands+='delete\nset memory xtboot_0_cfg 25 0\nstep 1500000\n'
        commands+='info hardware xtboot\ndump /i rom 0x800 0xfff 16\n'
    commands+='expression /X 0x6600c003\n'
    if verify_flash: commands+='dump /i rom 0x1800 0xffff 16\n'
    output=execute(executable,commands+'quit\n',wsl,timeout=120)
    name=f'{image}-crank-{pitch}-'+('uniform' if uniform else 'gap')
    log=RUNS/(name+'.log');log.write_text(output,encoding='utf-8',newline='\n')
    parts=re.split(r'(?m)^0x6600c00[123]\s*$',output)
    if len(parts)!=4: raise RuntimeError(f'Missing crank snapshots; see {log}')
    running=hex_memory(parts[1]); stopped=hex_memory(parts[2]) if loss else None
    def snapshot(m):
        word=lambda a:m[a]*256+m[a+1]
        return dict(synchronized=bool(m[sync]&128),sync_byte=m[sync],phase=m[phase],
                    pitch_ticks=word(pitch_ram),three_pitch_ticks=word(three_ram),
                    authentication_inhibit=bool(m[0xd21 if late else 0xd08]&1),
                    checksum_fault=bool(m[0x8b4 if late else 0x8b2]&128),
                    sidestand_inhibit=bool(m[0x88c]&128),
                    lean_sensor_fault=bool(m[0x8b3 if late else 0x8b1]&16))
    trace=events(parts[0])
    with (RUNS/(name+'.csv')).open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=('cycle','kind','channel','value','pc'))
        writer.writeheader();writer.writerows(trace)
    pulse_edges=[e for e in trace if e['kind']=='input' and e['value']==0]
    captures=[e for e in trace if e['kind']=='capture' and e['channel']==1]
    outputs={str(ch):[e for e in trace if e['kind']=='output' and e['channel']==ch] for ch in (3,6,7)}
    stops=re.findall(r'Stop at 0x([0-9a-fA-F]+): \((\d+)\)',parts[0])
    clean='FAULT=1' not in output and 'unmodelled' not in output and 'Parser error' not in output
    completed=bool(len(stops)==2 and all((int(a,16),int(c))==(loop,104) for a,c in stops)
                   and len(pulse_edges)==patterns*11 and clean)
    report=dict(image=image,sha256=record['sha256'],completed=completed,
                fixture=dict(pitch_timer_ticks=pitch,timer_prescaler=32,patterns=patterns,
                             intervals='uniform' if uniform else 'ten ordinary, one double',
                             adc=inputs,port_a_inputs=224,port_s_inputs=16,
                             storage='disconnected SPI; FF receive bytes',serial='idle; no peer'),
                falling_edges=len(pulse_edges),captures=len(captures),running=snapshot(running),
                after_pulse_loss=snapshot(stopped) if stopped else None,
                output_transitions={ch:len(rows) for ch,rows in outputs.items()},
                ignition_edges=[dict(cycle=e['cycle'],level=e['value']) for e in outputs['3']],
                trace=str(log),event_csv=str(RUNS/(name+'.csv')))
    if verify_flash:
        actual=hex_memory(parts[3])
        if len(actual)!=0xe800 or bytes(actual[a] for a in range(0x1800,0x10000))!=memory[0x1800:]:
            raise RuntimeError('Crank run changed source firmware bytes')
        report['flash_bytes_unchanged']=0xe800
    return report,trace
