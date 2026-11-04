"""Single pressure-producer preemption at every consumer instruction boundary.

Executes actual producer instructions with a separate saved CPU context/stack.
This bounded interleaving analysis does not emulate ADC conversion latency,
bus cycles, repeated interrupts or the complete interrupt entry/exit sequence.
"""
import argparse
import hashlib
import json
from pathlib import Path

from test_operating_sequences import Sequence
from test_pressure_sources import LAYOUTS, setup, track, lookup, rescale
from test_firmware_lookups import load_code, rd, wr

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT/'analysis/firmware/pressure_interleaving_validation.json'


def interrupt(r, ranges):
    assert not r.reg[49]&16, 'masked preemption'
    irq = Sequence(r.image, r.code)
    irq.ram = r.ram
    irq.stack = 0x1500
    for bounds in ranges: irq.run(bounds)
    r.executed.update(irq.executed)


def preempt(r, bounds, at, producer):
    def before(pc, index):
        if index == at: interrupt(r, producer)
    r.before_instruction = before
    try: r.run(bounds)
    finally: r.before_instruction = None


def window(r, l):
    old = [30000+i*1000 for i in range(5)]
    def fixture(slot):
        setup(r, l); m = r.ram
        first = m[l['index']]
        for i, v in enumerate(old): wr(m, l['history']+2*(first+i), 2, v)
        wr(m, l['previous'], 2, 40000)
        wr(m, l['spread'], 2, 65535)
        m[l['sync']], m[l['phase']], m[l['cycle']] = 128, 0, first+slot
        wr(m, l['adc'], 2, 50000)
        return m
    fixture(0); r.run(l['track']); trace = r.trace[:]
    reads = [i for i, a in enumerate(trace) if r.code[a]['assembly'] == 'LDD 0,IX'][:5]
    assert len(reads) == 5
    outcomes = set(); cases = 0
    for slot in range(5):
        for at in range(len(trace)):
            m = fixture(slot)
            expected = old[:]
            if at <= reads[slot]: expected[slot] = 50000
            preempt(r, l['track'], at, [l['store']])
            copied = tuple(rd(m, l['samples']+2*i, 2) for i in range(5))
            assert copied == tuple(expected), (slot, at, copied, expected)
            mean = sum(expected)//5
            assert rd(m, l['mean'], 2) == mean
            assert rd(m, l['tracked'], 2) == track(40000, mean, m[l['track_gain']])
            outcomes.add(copied); cases += 1
    return cases, len(outcomes)


def load_filter(r, l):
    def fixture():
        setup(r, l); m = r.ram
        for name, v in [('target', 20000), ('target2', 22000), ('filtered', 18000),
                        ('filtered2', 19000), ('estimate', 40000)]: wr(m, l[name], 2, v)
        m[l['phase']] = 1 if m[l['phase_config'][1]] == 128 else 0
        m[l['mode']] = 1
        wr(m, l['history']+2*m[l['index_config'][1]], 2, 50000)
        return m
    fixture(); r.run(l['filter']); trace = r.trace[:]
    read1 = next(i for i, a in enumerate(trace) if r.code[a]['assembly'] == f"LDD 0x{l['target']:x}")
    read2 = next(i for i, a in enumerate(trace) if r.code[a]['assembly'] == f"LDD 0x{l['target2']:x}")
    outcomes = set()
    for at in range(len(trace)):
        m = fixture()
        a, b = (50000 if at <= read1 else 20000), (50000 if at <= read2 else 22000)
        preempt(r, l['filter'], at, [l['sample'], l['instantaneous']])
        gain = lookup(m, l['table'], 40000)
        expected = (track(18000, a, m[l['filter_gain']]), track(19000, b, m[l['filter_gain']]))
        assert (rd(m, l['filtered'], 2), rd(m, l['filtered2'], 2)) == expected, (at, expected)
        assert rd(m, l['load'], 2) == rescale(expected[0], gain)
        assert rd(m, l['instant_load'], 2) == rescale(50000, gain)
        outcomes.add((a, b))
    return len(trace), sorted(outcomes)


def alternate(r, l):
    def fixture():
        setup(r, l); m = r.ram
        m[l['sync']], m[l['phase']], m[l['cycle']] = 128, 0, m[0x1870]
        wr(m, l['history']+2*m[0x1870], 2, 30000)
        wr(m, l['adc'], 2, 50000)
        wr(m, 0xCB6, 2, 40000)
        m[0xB3A] = 255
        for a in (0x1874, 0x1878, 0x187C): wr(m, a, 2, 0); wr(m, a+2, 2, 65535)
        return m
    bounds = (0xB209, 0xB2C9)
    fixture(); r.run(bounds); trace = r.trace[:]
    read = next(i for i, a in enumerate(trace) if r.code[a]['assembly'] == 'LDD 0,IX')
    for at in range(len(trace)):
        m = fixture(); source = 50000 if at <= read else 30000
        preempt(r, bounds, at, [l['store']])
        offset = lookup(m, 0x1880, rd(m, 0x900, 2))
        expected = max(0, min(65535, source+64*(offset-128)))
        assert rd(m, 0xCB2, 2) == source
        assert rd(m, 0xCB4, 2) == expected
        assert rd(m, 0xCB6, 2) == track(40000, expected, m[0x1872])
    return len(trace)


def build():
    codes = {f:load_code(f) for f in LAYOUTS}; results = []
    for e in json.loads((ROOT/'analysis/firmware/catalog.json').read_text())['images']:
        raw = (ROOT/e['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == e['sha256']
        family = e['code_family']; l = LAYOUTS[family]
        r = Sequence(b'\xff'*e['base_address']+raw, codes[family])
        n, windows = window(r, l); f, pairs = load_filter(r, l)
        checks = dict(window_copy_preemption=n, filter_preemption=f)
        if family == 'early': checks['alternate_estimator_preemption'] = alternate(r, l)
        results.append(dict(id=e['id'], firmware_sha256=e['sha256'], checks=checks,
            window_outcomes=windows, filter_source_pairs=pairs,
            instruction_addresses=[f'0x{a:04X}' for a in sorted(r.executed)]))
        print(e['id'], checks, flush=True)
    return dict(result='passed', cases=sum(sum(e['checks'].values()) for e in results), images=results,
        test_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        dependencies={n:hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest() for n in
            ['test_operating_sequences.py','test_pressure_sources.py','test_full_lift.py']},
        limits=['One producer invocation at each consumer instruction boundary in the selected fixtures',
                'Saved CPU context modeled with separate interpreter registers/stack',
                'No ADC/timer hardware, repeated interrupt streams or bus-cycle simulation'])


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--check', action='store_true'); args = ap.parse_args()
    result = build()
    if args.check: assert json.loads(REPORT.read_text()) == result, 'Pressure interleaving report is stale'
    else: REPORT.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    print('Pressure interleavings:', result['cases'], 'passed')
