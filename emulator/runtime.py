"""Bounded execution from reset into the normal firmware loop; no ECU access."""
import re
from runner import RUNS, execute, prepare, registered_image
from sensors import LATE_IMAGES


def runtime(executable,image,wsl=False,loops=100,steps=2000000,inputs=None,verify_flash=False):
    if not 1<=loops<=10000 or not 1<=steps<=10000000:
        raise ValueError('Runtime bounds: 1..10000 loop entries, 1..10000000 instructions.')
    inputs=[512]*8 if inputs is None else inputs
    if len(inputs)!=8 or any(type(v) is not int or not 0<=v<=1023 for v in inputs):
        raise ValueError('Supply eight ADC values in 0..1023.')
    record,setup=prepare(image,wsl)
    if image=='xt660-2004-2006-companion': loop=0x538b
    elif image in LATE_IMAGES: loop=0x4bc5
    else: raise ValueError('No reviewed main-loop entry for this image.')
    _,data=registered_image(image)
    memory=bytes(record['base_address'])+data
    if memory[loop+8:loop+13]!=bytes.fromhex('ce0ffeb757'):
        raise ValueError('Main-loop entry bytes do not match this profile.')
    # Pin fixtures only. Firmware and its initialized RAM are left untouched.
    commands=setup+'set memory xtboot_0_cfg 9 0xe0\nset memory xtboot_0_cfg 13 0x10\n'
    commands+=''.join(f'adc{n}={v}\n' for n,v in enumerate(inputs))
    commands+=f'break {loop} {loops}\nstep {steps}\ninfo hardware xtboot\n'
    if verify_flash: commands+='dump /i rom 0x1800 0xffff 16\n'
    output=execute(executable,commands+'quit\n',wsl,timeout=120)
    log=RUNS/f'{image}-runtime.log';log.write_text(output,encoding='utf-8')
    stops=re.findall(r'Stop at 0x([0-9a-fA-F]+): \((\d+)\)',output)
    stopped_at_loop=bool(stops and (int(stops[-1][0],16),int(stops[-1][1]))==(loop,104))
    clean='FAULT=0' in output and 'FAULT=1' not in output and 'unmodelled' not in output
    fields=('ADC_CONVERSIONS','ADC_SEQUENCES','IRQ_COUNT','CAPTURES','COMPARES','RTI_EVENTS','COP_SERVICES','SPI_BYTES','SPI_DROPPED')
    counts={}
    for name in fields:
        match=re.search(r'\b'+name+r'=(\d+)',output)
        if not match: raise RuntimeError(f'Missing runtime status {name}; see {log}')
        counts[name.lower()]=int(match[1])
    report={'image':image,'sha256':record['sha256'],'main_loop':f'0x{loop:04X}',
            'main_loop_entries':loops if stopped_at_loop else None,'completed':stopped_at_loop and clean,
            'fixture':{'adc':inputs,'port_a_inputs':224,'port_s_inputs':16,'spi':'disconnected/pulled-high MISO; no persistent storage model','serial':'idle; no peer','crank':'no edges'},
            'counts':counts,'trace':str(log)}
    if verify_flash:
        actual={}
        for match in re.finditer(r'(?m)^:([0-9a-fA-F]+)\s*$',output):
            block=bytes.fromhex(match[1])
            if sum(block)%256: raise RuntimeError('Invalid simulator HEX dump')
            if block[3]==0:
                address=int.from_bytes(block[1:3],'big')
                actual.update({address+n:v for n,v in enumerate(block[4:-1])})
        expected=memory[0x1800:]
        if len(actual)!=len(expected) or bytes(actual[a] for a in range(0x1800,0x10000))!=expected:
            raise RuntimeError('Runtime flash bytes differ from the registered source')
        report['flash_bytes_unchanged']=len(expected)
    return report
