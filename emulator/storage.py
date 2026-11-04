"""External storage fixtures derived by executing each BIN's initializer."""
import hashlib
from runner import RUNS, prepare, registered_image, execute
from crank import hex_memory


def factory_storage(executable, image, wsl=False):
    record, setup = prepare(image, wsl)
    _, data = registered_image(image)
    memory = bytes(record['base_address']) + data
    early = record['application_entry'] == 0x5000
    start, end = (0x5843, 0x5854) if early else (0x5019, 0x502a)
    calls = [0x5857, 0x5a13, 0x5c05, 0x5d4d, 0x5d77] if early else [0x502d, 0x5114, 0x5309, 0x5454, 0x5481]
    expected = b''.join(b'\x16'+x.to_bytes(2,'big') for x in calls) + b'\x14\x10\x06' + end.to_bytes(2,'big')
    if memory[start:start+len(expected)] != expected:
        raise ValueError('Unreviewed storage initializer')
    # An isolated call establishes only external defaults. Then the engine
    # session resets and runs its own startup; no runtime RAM is carried over.
    command = setup + 'fill rom 0x800 0xfff 0\nset memory xtboot_0_cfg 18 2\n'
    command += 'set memory xtboot_0_cfg 13 16\nset memory rom 0xda 3\nSP=0xff0\nCC=0xd0\n'
    command += f'break {end}\npc {start}\nstep 1000000\ninfo hardware xtboot\ndump /i eeprom 0 511 16\nquit\n'
    output = execute(executable, command, wsl, timeout=60)
    (RUNS / (image+'-storage-init.log')).write_text(output, encoding='utf-8', newline='\n')
    if f'Stop at 0x{end:06x}: (104)' not in output or 'FAULT=0' not in output or 'unmodelled' in output:
        raise RuntimeError('Firmware storage initialization did not complete')
    parsed = hex_memory(output)
    if len(parsed) != 512:
        raise RuntimeError('Incomplete storage dump')
    contents = bytes(parsed[i] for i in range(512))
    return contents, dict(initializer=f'0x{start:04X}', sha256=hashlib.sha256(contents).hexdigest(),
                         origin='Firmware default-writing routine; not a physical ECU EEPROM dump')


def storage_commands(contents, registered=False):
    if len(contents) != 512:
        raise ValueError('Expected a 512-byte external storage fixture')
    contents = bytearray(contents)
    if registered:
        contents[0x50:0x5b] = b'ABC'*3 + b'\x5a\xa5'
    return ('set memory xtboot_0_cfg 18 2\n' +
            ''.join(f'set memory eeprom {i} '+' '.join(str(x) for x in contents[i:i+32])+'\n'
                    for i in range(0,512,32)))
