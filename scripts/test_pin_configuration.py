"""Replay pin setup, service selectors and the late PB5 gate for every BIN.

Uses the CPU12 instruction interpreter, with bytes checked against each image.
Stops before entering the checksum/RAM tests or the intentional halt loop.
Peripheral electrical behavior is outside this software test.
"""
import argparse
import hashlib
import itertools
import json
import random
import re
import csv
from pathlib import Path
from test_speed_sources import Replay
from test_firmware_lookups import load_code, reference, wr

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/firmware/pin_configuration_validation.json'


def static_review(family):
    """Bound absence claims to direct operands in the decoded application."""
    path = 'analysis/disassembly.tsv' if family == 'early' else 'analysis/firmware/families/late/disassembly.tsv'
    rows = list(csv.DictReader((ROOT/path).open(), delimiter='\t'))
    found = {}
    for row in rows:
        # An indexed offset, immediate value or branch destination is not MMIO.
        op = row['instruction'].split()[0]
        if op.startswith(('J', 'LB')) or op in ('BRA','BEQ','BNE','BCS','BCC','BHI','BLS','BGE','BLT','BGT','BLE','BPL','BMI','BSR','BVC','BVS'):
            continue
        match = re.fullmatch(r'\w+ (0x[0-9a-f]+)(?:,0x[0-9a-f]+(?:,0x[0-9a-f]+)?)?', row['instruction'])
        if match:
            found.setdefault(int(match[1],16), []).append(row)
    early = family == 'early'
    expected = {2: [0x501E if early else 0x481E], 3: [0x5031 if early else 0x4826],
                9: [0x504D if early else 0x4842], 0x33: [0x5051 if early else 0x4846],
                0xE2: [0x5041 if early else 0x4836], 0xE8: [0x5045 if early else 0x483A],
                0xEA: [0x5049 if early else 0x483E], 0xF2: [0x5039 if early else 0x482E],
                0xA: [], 0xB: [], 0x1E: [], 0x32: [], 0x50: [], 0x58: [], 0xD9: []}
    for register, addresses in expected.items():
        assert [int(r['address'],16) for r in found.get(register,[])] == addresses, (family, register)
    # Whole-port initialization and dedicated set/clear masks cannot change the
    # PT0/PT4, PP5 or PS7 findings without invalidating this audit.
    assert all(r['instruction'].startswith(('STAA','STAB')) or
               re.fullmatch(r'B(?:SET|CLR) 0x00e0,0x80',r['instruction']) for r in found[0xE0])
    assert len([r for r in found[0xE0] if r['instruction'].startswith(('STAA','STAB'))]) == 1
    for row in found[0xF0]:
        if row['instruction'].startswith(('BSET','BCLR','BRSET','BRCLR')):
            mask = int(row['instruction'].split(',')[1],16)
            assert not mask & (0x60 if early else 0x20)
        else:
            assert int(row['address'],16) == (0x5035 if early else 0x482A)
    return dict(scope='Direct register operands in decoded application instructions; not a proof that arbitrary indirect accesses or external circuitry are absent.',
                references={f'0x{reg:04X}':[dict(address='0x'+r['address'].upper(),bytes=r['bytes'],instruction=r['instruction']) for r in found.get(reg,[])] for reg in expected})


def selector(replay, family, value, allowed):
    early = family == 'early'
    pc = 0xA2B9 if early else 0x951A
    exits = {0xA2E1: 'checksum', 0xA2F7: 'halt', 0xA505: 'ram_test', 0xA30F: 'none'} if early else {
        0x9542: 'checksum', 0x9558: 'halt', 0x9799: 'ram_test', 0x9570: 'none'}
    replay.ram[0] = value
    replay.ram[0x8B1 if early else 0x8B3] = 0x80 if allowed else 0
    expected = {0: 'halt', 0x40: 'ram_test', 0x80: 'checksum'}.get(value & 0xE0, 'none') if allowed else 'none'
    for _ in range(60):
        if pc in exits:
            assert exits[pc] == expected, (family, value, allowed, hex(pc), expected)
            return
        row = replay.code[pc]
        raw = bytes.fromhex(row['bytes'])
        assert replay.image[pc:pc + len(raw)] == raw
        replay.executed.add(pc)
        result, pc = reference(row, replay.ram, replay.reg)
        assert result == 0
    raise AssertionError('Selector did not reach a reviewed exit')


def pb5(replay, setup):
    m = replay.ram
    initial, overrides, enabled, stopped, elapsed, delay, load, limit, faults, pressure, coolant = setup
    m[1] = initial
    m[0x8A3] = 4 if overrides & 1 else 0
    m[0x8B4] = 0x80 if overrides & 2 else 0
    m[0x37E8] = enabled
    m[0x881] = 0x10 if stopped else 0
    wr(m, 0x9B6, 2, elapsed)
    wr(m, 0x9B4, 2, delay)
    wr(m, 0xCB2, 2, load)
    wr(m, 0x9B8, 2, limit)
    m[0x8B1] = (0x20 if faults & 1 else 0) | (0x10 if faults & 2 else 0)
    m[0x8B2] = 0x80 if faults & 4 else 0
    wr(m, 0xC62, 2, pressure << 8)
    m[0x8DC] = coolant
    high = enabled == 0x80 and not stopped and elapsed >= delay and load <= limit and not faults and 0x1A <= pressure < 0xF6 and 7 <= coolant < 0xF8
    expected = initial if overrides else (initial & 0xDF) | (0x20 if high else 0)
    replay.run((0xA90B, 0xA95E))
    assert m[1] == expected, (setup, m[1], expected)


def build():
    registry = json.loads((ROOT / 'analysis/firmware/catalog.json').read_text())
    codes = {f: load_code(f) for f in ('early', 'late')}
    results = []
    for entry in registry['images']:
        raw = (ROOT / entry['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry['sha256']
        image = b'\xFF' * entry['base_address'] + raw
        family = entry['code_family']; early = family == 'early'
        replay = Replay(image, codes[family])
        replay.run((0x5000, 0x5083) if early else (0x4800, 0x489D))
        expected = {0: 0xF8, 1: 0xFF if early else 0x1F, 2: 0x1F, 3: 0xEC, 9: 0x9F,
                    0x33: 0x80, 0x40: 0xD8, 0x48: 0xF0 if early else 0x30, 0x49: 0x80,
                    0xE0: 0xFE if early else 0xF6, 0xE2: 0xD9, 0xE8: 0xFF, 0xEA: 0xEA,
                    0xEE: 0x0A, 0xF0: 0xE0 if early else 0xA0, 0xF2: 0xFF, 0xD8: 0x50}
        assert {a: replay.ram[a] for a in expected} == expected
        assert replay.ram[0xD9] == 0 and replay.ram[0xA0] == 0
        # Both early branches initialize the newly reviewed PB2/3/5/6 outputs high.
        setup_cases = 1
        if early:
            replay.ram[0x18D3] = 8
            replay.run((0x5020, 0x5033))
            assert replay.ram[1] == 0xFD and replay.ram[3] == 0xEC
            setup_cases += 1
        for value, allowed in itertools.product(range(256), (False, True)):
            selector(replay, family, value, allowed)
        output_cases = 0
        if not early:
            assert image[0x37E8] == 0x80
            # Exhaust both pin states, preserve all neighboring bits, test every
            # raw boundary and both output-preserving override flags.
            for initial, overrides, pressure, coolant in itertools.product(
                    (0, 0x20, 0xDF, 0xFF), range(4), (0x19, 0x1A, 0xF5, 0xF6), (6, 7, 0xF7, 0xF8)):
                pb5(replay, (initial, overrides, 0x80, False, 100, 100, 100, 100, 0, pressure, coolant))
                output_cases += 1
            rng = random.Random(6605)
            for _ in range(2048):
                pb5(replay, (rng.randrange(256), rng.randrange(4), rng.choice((0x80, 0, 0xFF)), rng.randrange(2),
                             rng.randrange(65536), rng.randrange(65536), rng.randrange(65536), rng.randrange(65536),
                             rng.randrange(8), rng.randrange(256), rng.randrange(256)))
                output_cases += 1
            # Individual false conditions must each clear the output without an override.
            good = [0xFF, 0, 0x80, False, 100, 100, 100, 100, 0, 0x80, 0x80]
            for field, value in [(2, 0), (3, True), (4, 99), (6, 101), (8, 1), (8, 2), (8, 4)]:
                case = good.copy(); case[field] = value; pb5(replay, case); output_cases += 1
        executed = sorted(replay.executed)
        results.append(dict(id=entry['id'], sha256=entry['sha256'], family=family,
                            setup_cases=setup_cases, selector_cases=512, pb5_cases=output_cases,
                            checked_instructions=len(executed),
                            executed_bytes_sha256=hashlib.sha256(b''.join(image[a:a + len(bytes.fromhex(codes[family][a]['bytes']))] for a in executed)).hexdigest()))
    return dict(schema_version=1, result='passed', source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                configuration_source_sha256=hashlib.sha256((ROOT/'scripts/pin_configuration.py').read_bytes()).hexdigest(),
                dependencies={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in (
                    'scripts/test_speed_sources.py', 'scripts/test_firmware_lookups.py', 'scripts/test_full_lift.py',
                    'analysis/full/instructions.jsonl', 'analysis/firmware/families/late/full/instructions.jsonl.gz')},
                scope='Instruction execution only; no ECU is connected and no BIN is modified. Service-selector tests stop before destructive test/halt targets.',
                static_reviews={f: static_review(f) for f in codes},
                images=results, total_cases=sum(r['setup_cases']+r['selector_cases']+r['pb5_cases'] for r in results))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--check', action='store_true'); args = parser.parse_args()
    result = build(); content = json.dumps(result, indent=2) + '\n'
    if args.check:
        assert OUT.read_text() == content, 'Pin configuration validation is stale'
    else:
        OUT.write_text(content, encoding='utf-8', newline='\n')
    print(f"Checked pin setup, service selectors and PB5 gate: {result['total_cases']} cases across all nine BINs.")
