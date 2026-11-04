"""Run reviewed, unchanged firmware sensor routines with raw ADC inputs."""
import re
from runner import RUNS, execute, prepare, registered_image


LATE_IMAGES = {'xt660-5vk-1x-2008', 'xt660-2c1-10', 'xt660-2c1-10-immo-off', 'xt660-5vk-11'}


def sensor_demo(executable, image, inputs, wsl=False):
    if len(inputs)!=8 or any(type(v) is not int or not 0<=v<=1023 for v in inputs):
        raise ValueError('Supply eight integer ADC inputs, each from 0 to 1023.')
    record, setup = prepare(image,wsl)
    early = image=='xt660-2004-2006-companion'
    if not early and image not in LATE_IMAGES:
        raise ValueError('No reviewed sensor-routine profile for this image.')
    _, data = registered_image(image)
    memory = bytes(record['base_address'])+data
    start, reader = (0x56d0,0x5728) if early else (0x4f31,0x4f52)
    outputs = list(range(0xe3e,0xe5a,2)) if early else list(range(0xed2,0xee0,2))+[0xee6]
    if memory[reader:reader+4] != bytes.fromhex('4e86800b'):
        raise ValueError('Sensor routine does not match the reviewed entry bytes.')
    # Isolated subroutine calls: no startup bypass is advertised as normal boot.
    script = setup + 'fill rom 0x800 0xfff 0\nset memory rom 0x82 0x80\nset memory rom 9 0x0c\nSP=0xff0\nCC=0xd0\n'
    script += ''.join(f'adc{n}={value}\n' for n,value in enumerate(inputs))
    script += f'set memory rom 0x1000 0x16 {start>>8} {start&255} 0x16 {reader>>8} {reader&255} 0xa7\nbreak 0x1006\n'
    script += 'pc 0x1000\nstep 3000\n' * (4 if early else 1)
    script += 'expression /X (0x67000000+((PC==0x1006)&&(SP==0xff0)))\n'
    script += ''.join(f'expression /X (0x68000000+({n}<<16)+(rom[{a}]*256+rom[{a+1}]))\n' for n,a in enumerate(outputs))
    script += 'info hardware xtboot\nquit\n'
    output = execute(executable,script,wsl)
    log=RUNS/f'{image}-sensors.log'
    log.write_text(output)
    if 'FAULT=0' not in output or 'FAULT=1' in output or 'unmodelled' in output or not re.search(r'(?m)^0x67000001\s*$',output):
        raise RuntimeError(f'Sensor routine did not return cleanly; see {log}')
    values=[int(v,16) for v in re.findall(r'(?m)^0x(68[0-9a-fA-F]{6})\s*$',output)]
    if len(values)!=len(outputs) or any((v-0x68000000)>>16!=n for n,v in enumerate(values)):
        raise RuntimeError(f'Incomplete sensor output; see {log}')
    return {'image':image, 'sha256':record['sha256'],
            'scope':'isolated firmware sensor routine; raw ADC values, not a running engine',
            'adc_inputs':inputs,
            'ram_results':{f'0x{a:04X}':v&65535 for a,v in zip(outputs,values)},
            'trace':str(log)}
