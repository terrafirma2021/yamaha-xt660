"""Byte-checked CPU12 replay of pressure sampling and load construction.

Independent integer models, synthetic inputs, all registered BINs. The ADC
fixture starts at the stored-result consumer, not an emulated analog peripheral.
No physical pressure conversion or whole-engine validation is implied.
"""
import argparse
import hashlib
import json
import random
from pathlib import Path

from test_speed_sources import Replay
from test_firmware_lookups import load_code, rd, wr

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'analysis/firmware/pressure_source_validation.json'
ORIGIN = 7863
LAYOUTS = {
    'early': dict(store=(0xE385, 0xE3BE), sync=0xBFE, phase=0xC04,
                  cycle=0x922, adc=0x8CC, last=0xC40, short=0xC42, history=0xC58,
                  track=(0x869E, 0x87E6), index=0x189A, spread=0x189C,
                  track_gain=0x189E, bounds=0x18A0, samples=0xCB8,
                  extrema=0xCC2, mean=0xCC6, tracked=0xCC8, previous=0xCCA,
                  busy=0x8C0, faults=0x8AF, request=0x89F,
                  throttle=0x8E8, speed=0x900, load=0xC90,
                  select=(0xB304, 0xB381), counter=0xB3B, threshold=0x1843,
                  fallback=0xDA8, replacement=0xCA4, limits=0x18AC, estimate=0x8F2,
                  sample=(0xE431, 0xEA1B), phase_exit=0xEAD9,
                  phase_config=(0x18CE, 0xD8B), count_config=(0x1845, 0xD8D),
                  index_config=(0x184C, 0xD94), mode=0xCA8,
                  unsynced=0xC88, target=0xC8A, target2=0xC94,
                  instantaneous=(0xEA1B, 0xEA7F), instant_load=0xC8C,
                  filter=(0x95A6, 0x9661), filter_gain=0x1852,
                  filtered=0xC8E, filtered2=0xC96, substitute2=0xC98,
                  table=0x1854, table_ram=0xDBA, selected_gain=0xC92),
    'late': dict(store=(0xDCC1, 0xDCFA), sync=0xC20, phase=0xC26,
                 cycle=0x942, adc=0x8D2, last=0xC62, short=0xC64, history=0xC7A,
                 track=(0x7A63, 0x7BAB), index=0x1875, spread=0x1876,
                 track_gain=0x1878, bounds=0x187A, samples=0xCD2,
                 extrema=0xCDC, mean=0xCE0, tracked=0xCE2, previous=0xCE4,
                 busy=0x8C2, faults=0x8B1, request=0x8A1,
                 throttle=0x8F2, speed=0x920, load=0xCB2,
                 select=(0xAA41, 0xAAAC), counter=0xB70, threshold=0x184A,
                 fallback=0xE10, replacement=0xCC6, limits=0x1886, estimate=0x900,
                 sample=(0xDD6D, 0xDF0E), phase_exit=0xDFCC,
                 phase_config=(0x18A8, 0xDE7), count_config=(0x184B, 0xDE8),
                 index_config=(0x1852, 0xDEF), mode=0xCCA,
                 unsynced=None, target=0xCAC, target2=0xCB6,
                 instantaneous=(0xDF0E, 0xDF72), instant_load=0xCAE,
                 filter=(0x8A05, 0x8AC0), filter_gain=0x1858,
                 filtered=0xCB0, filtered2=0xCB8, substitute2=0xCBA,
                 table=0x185A, table_ram=0xE32, selected_gain=0xCB4),
}


def clamp(value, lo=0, hi=65535):
    return max(lo, min(hi, value))


def track(previous, target, gain):
    step = abs(target - previous) * gain // 256
    return previous + step if target >= previous else previous - step


def rescale(value, gain):
    step = (abs(value - ORIGIN) * gain * 2 + 128) // 256
    return clamp(ORIGIN + (step if value >= ORIGIN else -step))


def lookup(memory, table, value):
    minimum, span, factor = (rd(memory, table + n, 2) for n in (0, 2, 4))
    position = clamp(value - minimum, 0, span) * factor // 256
    index, fraction = divmod(position, 256)
    a = memory[table + 6 + index]
    if not fraction:
        return a
    b = memory[table + 7 + index]
    return (a * 256 + (b - a) * fraction) // 256


def reset(replay):
    replay.ram[:] = bytes(0x1800) + replay.image[0x1800:]
    replay.reg[:] = bytes(64)


def setup(replay, layout):
    reset(replay)
    m = replay.ram
    for rom, ram in (layout['phase_config'], layout['count_config'], layout['index_config']):
        m[ram] = m[rom]
    t, dest = layout['table'], layout['table_ram']
    m[dest:dest + 27] = m[t:t + 27]
    for n, key in enumerate(('throttle', 'speed', 'load')):
        low, high = (rd(m, layout['bounds'] + 4 * n + d, 2) for d in (0, 2))
        wr(m, layout[key], 2, (low + high) // 2)


def store_cases(replay, l):
    count = 0
    for synced in (False, True):
        for phase in range(11):
            for cycle in range(24):
                for failed in (False, True):
                    reset(replay)
                    m = replay.ram
                    m[l['sync']] = 128 if synced else 0
                    m[l['phase']], m[l['cycle']], m[0x88D] = phase, cycle, 2 if failed else 0
                    value = 10000 + 100 * cycle + phase
                    wr(m, l['adc'], 2, value)
                    replay.run(l['store'])
                    for start, slots, chosen in ((l['short'], 11, phase), (l['history'], 24, cycle)):
                        for index in range(slots):
                            expected = value if not failed and index == (chosen if synced else 0) else 0
                            assert rd(m, start + 2 * index, 2) == expected
                    assert rd(m, l['last'], 2) == (0 if failed else value)
                    count += 1
    return count


def track_case(replay, l, samples, old, gate=None, gain=None):
    setup(replay, l)
    m = replay.ram
    for i, value in enumerate(samples):
        wr(m, l['history'] + 2 * (m[l['index']] + i), 2, value)
    for key, value in [('previous', old), ('tracked', 12345), ('mean', 54321)]:
        wr(m, l[key], 2, value)
    m[0x881] = 2
    if gain is not None:
        m[l['track_gain']] = gain
    if gate:
        address, size, value = gate
        wr(m, address, size, value)
    accepted = not (m[l['faults']] & 0x3C or m[l['request']] & 128 or m[0x881] & 16)
    accepted &= max(samples) - min(samples) <= rd(m, l['spread'], 2)
    for n, key in enumerate(('throttle', 'speed', 'load')):
        lo, hi = (rd(m, l['bounds'] + 4 * n + d, 2) for d in (0, 2))
        accepted &= lo <= rd(m, l[key], 2) <= hi
    replay.run(l['track'])
    assert [rd(m, l['samples'] + 2 * i, 2) for i in range(5)] == samples
    assert (rd(m, l['extrema'], 2), rd(m, l['extrema'] + 2, 2)) == (max(samples), min(samples))
    assert not m[l['busy']] & 32 and not m[0x881] & 2
    expected = track(old, sum(samples) // 5, m[l['track_gain']]) if accepted else old
    assert rd(m, l['previous'], 2) == expected
    assert rd(m, l['tracked'], 2) == (expected if accepted else 12345)
    assert rd(m, l['mean'], 2) == (sum(samples) // 5 if accepted else 54321)
    return int(accepted)


def selection_cases(replay, l):
    count = 0
    for faults in range(64):
        for request in (0, 8, 128, 136):
            for startup in (False, True):
                setup(replay, l)
                m = replay.ram
                m[l['faults']], m[l['request']] = faults, request
                m[0x880] = 8 if startup else 0
                m[l['counter']] = m[l['threshold']]
                for key, value in [('fallback', 30000), ('replacement', 40000), ('tracked', 50000)]:
                    wr(m, l[key], 2, value)
                expected = 30000 if startup or request & 8 or faults & 0x3C else 40000 if request & 128 else 50000
                replay.run(l['select'])
                assert rd(m, l['estimate'], 2) == expected
                count += 1
    for value in (0, 1, 27519, 27520, 27521, 65279, 65280, 65281, 65535):
        setup(replay, l)
        wr(replay.ram, l['tracked'], 2, value)
        replay.run(l['select'])
        assert rd(replay.ram, l['estimate'], 2) == clamp(value, rd(replay.image, l['limits'], 2), rd(replay.image, l['limits'] + 2, 2))
        count += 1
    return count


def sample_cases(replay, l, family):
    count = 0
    for phase in (0, 1, 6, 10):
        for phase_config in (0, 128):
            for mode in (0, 1, 8, 9):
                for fault in (0, 4, 16, 32):
                    setup(replay, l)
                    m = replay.ram
                    m[l['phase']], m[l['phase_config'][1]] = phase, phase_config
                    m[l['mode']], m[l['faults']] = mode, fault
                    for i in range(24):
                        wr(m, l['history'] + 2 * i, 2, 30000 + i)
                    for i in range(11):
                        wr(m, l['short'] + 2 * i, 2, 10000 + i)
                    wr(m, l['target'], 2, 15000)
                    wr(m, l['target2'], 2, 16000)
                    wr(m, l['fallback'], 2, 50000)
                    if family == 'early':
                        wr(m, l['unsynced'], 2, 20000)
                    eligible = phase == (1 if phase_config == 128 else 0)
                    expected, second = 15000, 16000
                    if eligible:
                        if fault & 0x30:
                            expected = 50000
                        elif mode & 1:
                            expected = second = 30000 + m[l['index_config'][1]]
                        elif family == 'early':
                            expected = second = 20000
                        elif mode & 8:
                            expected = second = 10000 + m[l['index_config'][1]]
                    replay.run((l['sample'][0], l['sample'][1] if eligible else l['phase_exit']))
                    assert (rd(m, l['target'], 2), rd(m, l['target2'], 2)) == (expected, second)
                    if family == 'late' and eligible and not fault & 0x30 and mode == 8:
                        assert not m[l['mode']] & 8
                    count += 1
    return count


def load_case(replay, l, source, old, estimate, mode):
    setup(replay, l)
    m = replay.ram
    for key, value in [('target', source), ('filtered', old), ('estimate', estimate),
                       ('target2', 60000), ('filtered2', 20000), ('substitute2', 22222)]:
        wr(m, l[key], 2, value)
    m[l['mode']] = mode
    gain = lookup(m, l['table'], estimate)
    replay.run(l['instantaneous'])
    assert rd(m, l['instant_load'], 2) == rescale(source, gain)
    replay.run(l['filter'])
    filtered = track(old, source, m[l['filter_gain']])
    assert rd(m, l['filtered'], 2) == filtered
    assert rd(m, l['filtered2'], 2) == (track(20000, 60000, m[l['filter_gain']]) if mode & 1 else 22222)
    assert m[l['selected_gain']] == gain
    assert rd(m, l['load'], 2) == rescale(filtered, gain)


def build():
    catalog = json.loads((ROOT / 'analysis/firmware/catalog.json').read_text())
    codes = {f: load_code(f) for f in LAYOUTS}
    results = []
    for entry in catalog['images']:
        raw = (ROOT / entry['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry['sha256']
        image = b'\xff' * entry['base_address'] + raw
        family = entry['code_family']
        l = LAYOUTS[family]
        replay = Replay(image, codes[family])
        rng = random.Random(660031)
        checks = dict(adc_result_storage=store_cases(replay, l))
        accepted = 0
        gates = [None]
        gates += [(l['faults'], 1, v) for v in (1, 2, 4, 8, 16, 32, 64, 128, 255)]
        gates += [(l['request'], 1, v) for v in (8, 128, 255)] + [(0x881, 1, 16)]
        for n, key in enumerate(('throttle', 'speed', 'load')):
            lo, hi = (rd(image, l['bounds'] + 4 * n + d, 2) for d in (0, 2))
            gates += [(l[key], 2, v) for v in (lo - 1, lo, lo + 1, hi - 1, hi, hi + 1) if 0 <= v <= 65535]
        spread = rd(image, l['spread'], 2)
        for gate in gates:
            for width in (0, spread - 1, spread, spread + 1):
                samples = [40000, 40001 if width else 40000, 40000 + width, 40000, 40000]
                accepted += track_case(replay, l, samples, 30000, gate)
        checks['window_gate_boundaries'] = len(gates) * 4
        for gain in range(256):
            center = rng.randrange(65536 - spread)
            samples = [center + rng.randrange(spread + 1) for _ in range(5)]
            accepted += track_case(replay, l, samples, rng.randrange(65536), gain=gain)
        checks['window_tracking_all_gain_bytes'] = 256
        checks['estimate_priority_and_limits'] = selection_cases(replay, l)
        checks['phase_and_fault_sample_selection'] = sample_cases(replay, l, family)
        points = (0, 1, ORIGIN - 1, ORIGIN, ORIGIN + 1, 27520, 40000, 65280, 65535)
        for source in points:
            for old in points:
                for estimate in (0, 29183, 29184, 29185, 40001, 49664, 65535):
                    load_case(replay, l, source, old, estimate, (source + old) & 1)
        checks['linked_lookup_filters_both_load_outputs'] = len(points) ** 2 * 7
        t = l['table']
        results.append(dict(id=entry['id'], firmware_sha256=entry['sha256'], family=family,
                            checks=checks, accepted_tracking_cases=accepted,
                            executed_instructions=len(replay.executed),
                            stock=dict(window_first_index=image[l['index']], window_sample_count=5,
                                       max_window_spread=spread, window_gain=image[l['track_gain']],
                                       eligibility_bounds=[rd(image, l['bounds'] + n, 2) for n in range(0, 12, 2)],
                                       load_sample_count=image[l['count_config'][0]],
                                       load_sample_index=image[l['index_config'][0]],
                                       load_filter_gain=image[l['filter_gain']],
                                       gain_table_hex=image[t:t + 27].hex())))
    return dict(result='passed', cases=sum(sum(r['checks'].values()) for r in results), images=results,
                test_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                replay_script_sha256=hashlib.sha256((ROOT / 'scripts/test_speed_sources.py').read_bytes()).hexdigest(),
                interpreter_sha256=hashlib.sha256((ROOT / 'scripts/test_full_lift.py').read_bytes()).hexdigest(),
                scope='Byte-checked selected-path CPU12 replay, synthetic RAM/peripherals, stock one-sample load configuration. '
                      'ADC-result storage, complete five-sample eligibility/tracking, selected pressure priority, phase/fault '
                      'load selection, RAM curve lookup, filtering and signed rescale in both families. '
                      'Not analog pressure calibration, whole-ECU scheduling or on-engine validation.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    report = build()
    if args.check:
        assert json.loads(REPORT.read_text()) == report, 'stale pressure-source report'
    else:
        REPORT.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f"Pressure sources: {report['cases']} checks, {len(report['images'])} BINs passed.")
