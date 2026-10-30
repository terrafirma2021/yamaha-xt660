"""Byte-checked replay of configurable pressure calculation paths.

Synthetic RAM/calibration inputs exercise dormant branches without editing BINs.
This verifies their arithmetic and branch choices, not physical sensor units.
"""
import argparse
import hashlib
import json
import random
from pathlib import Path

from map_models import clamp
from test_pressure_sources import LAYOUTS, ORIGIN, setup, reset, track, lookup
from test_speed_sources import Replay
from test_firmware_lookups import load_code, rd, wr

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'analysis/firmware/alternate_path_validation.json'


def weighted_pressure(samples, weights, early):
    n = len(samples)
    if early:
        # The first sample has no unweighted term. Subsequent samples do.
        total = sum(s * w // 256 for s, w in zip(samples, weights)) + sum(samples[1:])
        return min(65535, total // n)
    terms = [(1 if s >= ORIGIN else -1) * (abs(s - ORIGIN) * w // 128)
             for s, w in zip(samples, weights)]
    total = sum(terms)
    return clamp(ORIGIN + (1 if total >= 0 else -1) * (abs(total) // n))


def multisample_cases(replay, l, early, rng):
    cases = 0
    examples = []
    # Every count byte is dispatched, including 0 and all unsupported counts.
    fixtures = [(n, [20000 + 1000 * i for i in range(6)], [128] * 6) for n in range(256)]
    for n in range(2, 7):
        for w in range(256):
            # Both signs around the later family's origin, extrema and carries.
            samples = ([0, 65535, ORIGIN - 1, ORIGIN, ORIGIN + 1, 32768]
                       if w % 3 == 0 else [0] * 6 if w % 3 == 1 else [65535] * 6)
            fixtures.append((n, samples, [w] * 6))
        for _ in range(64):
            fixtures.append((n, [rng.randrange(65536) for _ in range(6)],
                             [rng.randrange(256) for _ in range(6)]))
        fixtures.append((n, [20000] * 6, [0 if early else 128] * 6))
    for n, values, weights in fixtures:
        # Later code also uses this algorithm on its short-history refresh path.
        for mode in ((1,) if early else (1, 8)):
            setup(replay, l)
            m = replay.ram
            m[l['phase']] = 1 if m[l['phase_config'][1]] == 128 else 0
            m[l['mode']], m[l['count_config'][1]] = mode, n
            history = l['history'] if mode == 1 else l['short']
            indices = [5, 0, 4, 1, 3, 2]
            for i, (value, weight, index) in enumerate(zip(values, weights, indices)):
                wr(m, history + 2 * index, 2, value)
                m[l['index_config'][1] + i] = index
                m[(0xD8E if early else 0xDE9) + i] = weight
            replay.run(l['sample'])
            expected = weighted_pressure(values[:n], weights[:n], early) if 2 <= n <= 6 else values[0]
            assert rd(m, l['target'], 2) == expected, (early, n, mode, values, weights, rd(m, l['target'], 2), expected)
            assert rd(m, l['target2'], 2) == expected
            if mode == 8:
                assert m[l['mode']] == 0
            cases += 1
    for n in range(2, 7):
        weights = [0 if early else 128] * n
        examples.append(dict(count=n, samples=[20000] * n, weights=weights,
                             result=weighted_pressure([20000] * n, weights, early)))
    return cases, examples


def replacement_cases(replay, l, early, rng):
    start, stop = (0xB1A4, 0xB209) if early else (0xA9A1, 0xAA06)
    counter, threshold, gain, source = ((0xB3D, 0x18B0, 0x18B1, 0xCA2) if early
                                        else (0xB72, 0x188A, 0x188B, 0xCC4))
    cases = 0
    for count in (0, 1, 4, 5, 254, 255):
        for limit in (0, 1, 5, 255):
            for flags in (0, 64, 128, 192, 255):
                for states in range(4):
                    setup(replay, l)
                    m = replay.ram
                    current, previous = rng.randrange(65536), rng.randrange(65536)
                    m[counter], m[threshold], m[gain], m[l['request']] = count, limit, rng.randrange(256), flags
                    m[0x881] = 32 if states & 1 else 0
                    m[0x880] = 8 if states & 2 else 0
                    wr(m, source, 2, current)
                    wr(m, l['replacement'], 2, previous)
                    qualified = states == 1
                    new_count = min(255, count + 1) if qualified else 0
                    enabled = qualified and new_count >= limit
                    new_flags = flags | 192 if enabled else flags & ~192
                    expected = (track(previous, current, m[gain]) if flags & 64 else current) if enabled else previous
                    replay.run((start, stop))
                    assert m[counter] == new_count and m[l['request']] == new_flags
                    assert rd(m, l['replacement'], 2) == expected
                    cases += 1
    return cases


def alternate_estimator_cases(replay, l, rng):
    gates = [None]
    gates += [(0x8AF, 1, v) for v in (1, 2, 4, 8, 16, 32, 64, 128, 255)]
    gates += [(0x89F, 1, 128), (0x881, 1, 16), (0x1871, 1, 0), (0x1871, 1, 255)]
    for n, a in enumerate((0x8E8, 0x900, 0xC90)):
        lo, hi = (rd(replay.image, 0x1874 + 4 * n + d, 2) for d in (0, 2))
        gates += [(a, 2, v) for v in (lo - 1, lo, lo + 1, hi - 1, hi, hi + 1) if 0 <= v <= 65535]
    count = 0
    for gate in gates:
        for counter in (0, 24, 25, 26, 254, 255):
            for sync in (0, 128):
                setup(replay, l)
                m = replay.ram
                m[0xBFE], m[0xB3A] = sync, counter
                sample, prior_sample, target, previous = [rng.randrange(65536) for _ in range(4)]
                wr(m, 0xC58 + 2 * m[0x1870], 2, sample)
                wr(m, 0xCB2, 2, prior_sample)
                wr(m, 0xCB4, 2, target)
                wr(m, 0xCB6, 2, previous)
                # Inject non-flat curve cells to exercise the offset arithmetic.
                m[0x1886:0x189A] = bytes(rng.randrange(256) for _ in range(20))
                for n, a in enumerate((0x8E8, 0x900, 0xC90)):
                    lo, hi = (rd(m, 0x1874 + 4 * n + d, 2) for d in (0, 2))
                    wr(m, a, 2, (lo + hi) // 2)
                if gate:
                    wr(m, *gate)
                eligible = not (m[0x8AF] & 60 or m[0x89F] & 128 or m[0x881] & 16)
                for n, a in enumerate((0x8E8, 0x900, 0xC90)):
                    lo, hi = (rd(m, 0x1874 + 4 * n + d, 2) for d in (0, 2))
                    eligible &= lo <= rd(m, a, 2) <= hi
                new_count = min(255, counter + 1) if eligible else 0
                # Saturated counter takes the update branch even with limit 255.
                update = eligible and (counter == 255 or new_count > m[0x1871])
                chosen = sample if sync else prior_sample
                expected_target = clamp(chosen + 64 * (lookup(m, 0x1880, rd(m, 0x900, 2)) - 128)) if update else target
                expected = track(previous, expected_target, m[0x1872])
                replay.run((0xB209, 0xB2C9))
                assert m[0xB3A] == new_count
                assert rd(m, 0xCB2, 2) == chosen
                assert rd(m, 0xCB4, 2) == expected_target
                assert rd(m, 0xCB6, 2) == expected
                # Check the actual output-selection setting after this update.
                m[0x8AF] = m[0x89F] = m[0x880] = 0
                for selector in (0, 1, 127, 128, 129, 255):
                    m[0x186F] = selector
                    wr(m, 0xCC8, 2, 45000)
                    replay.run(l['select'])
                    selected = 45000 if selector == 128 else expected
                    assert rd(m, 0x8F2, 2) == clamp(selected, rd(m, 0x18AC, 2), rd(m, 0x18AE, 2))
                count += 1
    return count


def build():
    codes = {f: load_code(f) for f in LAYOUTS}
    results = []
    for entry in json.loads((ROOT / 'analysis/firmware/catalog.json').read_text())['images']:
        raw = (ROOT / entry['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry['sha256']
        image = b'\xff' * entry['base_address'] + raw
        family = entry['code_family']
        early = family == 'early'
        l = LAYOUTS[family]
        replay = Replay(image, codes[family])
        rng = random.Random(660044)
        multi, examples = multisample_cases(replay, l, early, rng)
        checks = dict(multisample=multi, pressure_replacement=replacement_cases(replay, l, early, rng))
        if early:
            checks['alternate_estimator_with_six_selector_values'] = alternate_estimator_cases(replay, l, rng)
        results.append(dict(id=entry['id'], firmware_sha256=entry['sha256'], family=family,
                            checks=checks, pressure_examples=examples, executed_instructions=len(replay.executed),
                            stock_sample_count=image[l['count_config'][0]],
                            stock_weights=list(image[0x1846:0x184C] if early else image[0x184C:0x1852]),
                            stock_estimator_selector=image[0x186F] if early else None))
        print(entry['id'], checks, flush=True)
    dependencies = ['test_pressure_sources.py', 'test_speed_sources.py', 'test_full_lift.py', 'map_models.py']
    return dict(result='passed', cases=sum(sum(x['checks'].values()) for x in results), images=results,
                test_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                dependencies={n: hashlib.sha256((ROOT / 'scripts' / n).read_bytes()).hexdigest() for n in dependencies},
                scope='Byte-checked selected-path CPU12 replay with synthetic RAM/calibration settings, all registered BINs. '
                      'Pressure sample-count dispatch and two-to-six-sample arithmetic, replacement latch/filter and early '
                      'alternate estimator. Not physical units, electrical sampling or whole-ECU interrupt timing.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    report = build()
    if args.check:
        assert json.loads(REPORT.read_text()) == report, 'stale alternate-path report'
    else:
        REPORT.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f"Alternate paths: {report['cases']} cases across {len(report['images'])} BINs passed.")
