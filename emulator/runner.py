"""Verified image loading and bounded uCsim execution; no physical ECU access."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / 'emulator/.runs'


def registered_image(image_id):
    records = json.loads((ROOT / 'firmware/registry.json').read_text())['images']
    record = next((r for r in records if r['id'] == image_id), None)
    if record is None:
        raise ValueError(f'Unknown registered image: {image_id}')
    data = (ROOT / record['file']).read_bytes()
    if hashlib.sha256(data).hexdigest() != record['sha256']:
        raise ValueError(f'Source hash mismatch: {image_id}')
    base = record['base_address']
    if base + len(data) != 0x10000:
        raise ValueError('Image does not end at the hardware vectors')
    memory = bytes(base) + data
    if memory[0xf800:] == b'\xff' * 0x800:
        raise ValueError('Boot code is absent in this BIN; no donor boot is inserted')
    if memory[0xfffe:] != b'\xf8\x00':
        raise ValueError('Reset vector is outside the reviewed boot profile')
    if memory[0xf7a0] != 0x06:
        raise ValueError('Application trampoline is outside the reviewed boot profile')
    entry = int.from_bytes(memory[0xf7a1:0xf7a3], 'big')
    if not 0x1800 <= entry < 0xf7a0:
        raise ValueError('Invalid application entry address')
    record = dict(record, application_entry=entry)
    return record, data


def ihex(data, base):
    lines = []
    for offset in range(0, len(data), 16):
        addr = base + offset
        block = data[offset:offset + 16]
        record = bytes([len(block), addr >> 8, addr & 255, 0]) + block
        lines.append(':' + record.hex().upper() + f'{-sum(record) & 255:02X}')
    return '\n'.join(lines + [':00000001FF', ''])


def target_path(path, wsl=False):
    path = Path(path).resolve()
    if wsl and os.name == 'nt':
        return '/mnt/' + path.drive[0].lower() + path.as_posix()[2:]
    return path.as_posix()


def execute(executable, commands, wsl=False, timeout=30):
    RUNS.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='ascii', suffix='.cmd',
                                     dir=RUNS, delete=False) as script:
        script.write(commands)
        path = Path(script.name)
    command = (['wsl', '-e'] if wsl else []) + [str(executable), '-q', '-R', '0',
                '-e', f'exec "{target_path(path, wsl)}"']
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, text=True,
                                capture_output=True, timeout=timeout)
    finally:
        path.unlink(missing_ok=True)
    if result.returncode:
        raise RuntimeError(f'Simulator exited {result.returncode}: {result.stderr[-2000:]}')
    return result.stdout + result.stderr


def prepare(image_id, wsl=False):
    record, data = registered_image(image_id)
    RUNS.mkdir(parents=True, exist_ok=True)
    path = RUNS / f'{image_id}.hex'
    path.write_text(ihex(data, record['base_address']), encoding='ascii')
    return record, f'file "{target_path(path, wsl)}"\nreset\n'


def boot(executable, image_id, wsl=False, steps=200000):
    record, setup = prepare(image_id, wsl)
    entry = record['application_entry']
    commands = (setup + f'fill rom 0x800 0xfff 0xa5\nbreak 0x{entry:04x}\n'
                f'step {steps}\ninfo hardware xtboot\ninfo registers\nquit\n')
    output = execute(executable, commands, wsl)
    log = RUNS / f'{image_id}.log'
    log.write_text(output)
    stops = re.findall(r'Stop at 0x([0-9a-fA-F]+): \((\d+)\)', output)
    reached = bool(stops and int(stops[-1][0], 16) == entry and stops[-1][1] == '104')
    reached = reached and 'FAULT=0' in output and 'XT660 unmodelled' not in output
    report = {
        'image': image_id, 'sha256': record['sha256'], 'base_address': record['base_address'],
        'application_entry_reached': reached,
        'application_entry': f'0x{entry:04x}',
        'stop_address': '0x' + stops[-1][0] if stops else None,
        'scope': 'reset to application entry; runtime ECU emulation is not implemented',
        'instruction_budget': steps,
    }
    (RUNS / f'{image_id}.json').write_text(json.dumps(report, indent=2) + '\n')
    return report, log, output
