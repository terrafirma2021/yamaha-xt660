"""Replay fuel mode dispatch, fixed requests/gains and blend qualification.

Synthetic settings exercise code branches absent from the stock mode-3 route.
No firmware files or hardware are modified. Calibration indices are kept valid.
"""
import argparse
import hashlib
import json
import random
from pathlib import Path

from map_models import primary_request, secondary_request, rounded_q8, clamp, q8
from test_speed_sources import Replay
from test_firmware_lookups import load_code, rd, wr

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'analysis/firmware/fuel_mode_validation.json'


def reset(replay):
    replay.ram[:] = bytes(0x1800) + replay.image[0x1800:]
    replay.reg[:] = bytes(64)


def late_post(memory, limited):
    if not memory[0xCCA] & 1:
        return rounded_q8(limited, memory[0x19AE] * 4)
    if memory[0x4124] == 128 and (memory[0xACF] & 4 or memory[0xAD0] & 32):
        return rounded_q8(limited, memory[0xAD7] * 2)
    return limited


def configuration(replay, early, rng, n):
    reset(replay)
    m = replay.ram
    lo, hi = sorted(rng.sample(range(65536), 2))
    for address, value in [(0x19DA if early else 0x19B4, lo),
                           (0x19DC if early else 0x19B6, hi),
                           (0x95E if early else 0x966, rng.randrange(65536))]:
        wr(m, address, 2, value)
    m[0x19D4 if early else 0x19AE] = rng.randrange(256)
    m[0xCA8 if early else 0xCCA] = n % 2
    if not early:
        m[0x4124] = (0, 128, 255)[(n // 2) % 3]
        m[0xACF] = 4 if (n // 6) % 2 else 0
        m[0xAD0] = 32 if (n // 12) % 2 else 0
        m[0xAD7] = rng.randrange(256)
    return m, lo, hi


def dispatch_cases(replay, early):
    mode_address = 0x19DE if early else 0x19B8
    for mode in range(256):
        reset(replay)
        m = replay.ram
        m[mode_address] = mode
        replay.run(((0x8031 if early else 0x76A3),
                    (0x803B if early else 0x76AD) if mode == 1 else (0x8152 if early else 0x773B)))
        if mode != 1:
            m[0x19E1 if early else 0x19BB] = 65
            m[0x19E2 if early else 0x19BC] = 129
            if early:
                m[0x19E3] = 193
            replay.run(((0x81E8 if early else 0x77D1),
                        (0x8319 if early else 0x7885) if mode in (2, 4) else (0x8220 if early else 0x77F8)))
            if mode in (2, 4):
                primary = 130 if mode == 2 else 258
                secondary = 130 if mode == 2 else 386
                assert rd(m, 0x960 if early else 0x968, 2) == primary
                assert rd(m, 0x964 if early else 0x96A, 2) == primary
                if early:
                    assert rd(m, 0x962, 2) == rd(m, 0x966, 2) == secondary
    return 256


def fixed_request_cases(replay, early, rng):
    for n in range(512):
        m, lo, hi = configuration(replay, early, rng, n)
        m[0x19DE if early else 0x19B8] = 1
        code = n % 256
        m[0x19DF if early else 0x19B9] = code
        compensation = rd(m, 0x95E if early else 0x966, 2)
        limited = clamp(code * 32, lo, hi)
        scaled = ((limited if m[0xCA8] & 1 else rounded_q8(limited, m[0x19D4] * 4))
                  if early else late_post(m, limited))
        final = clamp(scaled + compensation)
        if early:
            m[0x19E0] = 255 - code
            second_base = clamp((255 - code) * 32, lo, hi)
            channel_gain = (0, 1, 128, 254, 255)[n % 5]
            # Exercise the actual channel-gain lookup, with constant synthetic
            # cells so its independent expected output is unambiguous.
            m[0x1A1A:0x1ACE] = bytes([channel_gain]) * 180
            wr(m, 0x95A, 2, 12345)
            wr(m, 0x94A, 2, 23456)
            m[0xA16] = 3
        replay.run((0x8031, 0x8578) if early else (0x76A3, 0x79A0))
        assert rd(m, 0x940 if early else 0x95A, 2) == limited
        assert rd(m, 0x93E if early else 0x958, 2) == scaled
        assert rd(m, 0x92A if early else 0x948, 2) == final
        for a in ((0x960, 0x962, 0x964, 0x966) if early else (0x968, 0x96A)):
            assert rd(m, a, 2) == 256
        if early:
            assert m[0xCEC] == channel_gain and rd(m, 0x94C, 2) == second_base
            product = second_base * channel_gain * 2 + 128
            if product >= 1 << 24:
                assert rd(m, 0x95A, 2) == 12345 and rd(m, 0x94A, 2) == 23456
                second_final = 65535
            else:
                second_limited = clamp(product // 256, lo, hi)
                second_scaled = (second_limited if m[0xCA8] & 1
                                 else rounded_q8(second_limited, m[0x19D4] * 4))
                assert rd(m, 0x95A, 2) == second_limited and rd(m, 0x94A, 2) == second_scaled
                second_final = clamp(second_scaled + compensation)
            assert rd(m, 0x92C, 2) == rd(m, 0x946, 2) == second_final
            assert m[0xA16] & 3 == 0 and m[0x881] & 192 == 192
        else:
            assert not m[0xA28] & 1 and m[0x881] & 128
    return 512


def forced_gain_cases(replay, early, rng):
    cases = 0
    for mode in (2, 4):
        for code in range(256):
            for secondary in ((False, True) if early else (False,)):
                m, lo, hi = configuration(replay, early, rng, code)
                m[0x19DE if early else 0x19B8] = mode
                m[0x19E1 if early else 0x19BB] = code
                m[0x19E2 if early else 0x19BC] = code
                if early:
                    m[0x19E3] = 255 - code
                    m[0xA16] = 2 if secondary else 0
                gain = 2 * (255 - code if secondary and mode == 4 else code)
                qa, qb = [rng.randrange(65536) for _ in range(2)]
                additive, blend, channel_gain = [rng.randrange(256) for _ in range(3)]
                reduction = (0, 1, 1023, 1024, 65535)[code % 5]
                if early:
                    wr(m, 0xCE6 if secondary else 0xCE4, 2, qa)
                    wr(m, 0xCEA if secondary else 0xCE8, 2, qb)
                    m[0x95D if secondary else 0x95C] = additive
                    m[0x998], m[0xCEC] = blend, channel_gain
                    wr(m, 0xAD4, 2, reduction)
                    args = [qa, qb, gain, gain, additive, blend, reduction]
                    if secondary:
                        args.append(channel_gain)
                    args += [lo, hi, m[0x19D4], bool(m[0xCA8] & 1), rd(m, 0x95E, 2)]
                    expected = (secondary_request if secondary else primary_request)(*args)
                    replay.run((0x81E8, 0x8578))
                else:
                    wr(m, 0xCFE, 2, qa)
                    wr(m, 0xD00, 2, qb)
                    m[0x964], m[0x996] = additive, blend
                    a, b = [q8(clamp(value + 4 * (additive - 128)), gain) for value in (qa, qb)]
                    limited = clamp(b * blend // 256 + a * (255 - blend) // 256, lo, hi)
                    scaled = late_post(m, limited)
                    final = clamp(scaled + rd(m, 0x966, 2))
                    expected = {0x95C: a, 0x95E: b, 0x95A: limited, 0x956: limited,
                                0x958: scaled, 0x954: final, 0x948: final}
                    replay.run((0x77D1, 0x79A0))
                for a, value in expected.items():
                    assert rd(m, a, 2) == value, (early, mode, code, secondary, hex(a), rd(m, a, 2), value)
                cases += 1
    return cases


def blend_cases(replay, early, rng):
    start, stop = (0x8152, 0x81E8) if early else (0x773B, 0x77D1)
    table, index, threshold, hold = (0xC255, 0x19D6, 0x19D5, 0x19D8) if early else (0xBC32, 0x19B0, 0x19AF, 0x19B2)
    throttle, fault, counter, result = (0x8E8, 0x8AF, 0xB03, 0x998) if early else (0x8F2, 0x8B1, 0xB36, 0x996)
    fixtures = [(v, 0, 4, 255, 100, 2, 40) for v in range(256)]
    fixtures += [(50, f, p, c, 50, i, 40) for f in (0, 4, 8, 12, 16, 32, 60, 64)
                 for p in (0, 4) for c in (0, 39, 40, 255) for i in (0, 8, 255)]
    fixtures += [(rng.randrange(256), rng.randrange(256), rng.choice((0, 4)), rng.randrange(256),
                  rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(256)]
    for value, flags, enabled, count, th, ix, minimum_count in fixtures:
        reset(replay)
        m = replay.ram
        m[throttle], m[fault], m[0x88D], m[counter] = value, flags, enabled, count
        m[threshold], m[index], m[hold] = th, ix, minimum_count
        margin, multiplier = m[table + 2 * min(ix, 8):table + 2 * min(ix, 8) + 2]
        advance = False
        if flags & 48:
            expected, advance = 255, True
        elif flags & 12 or not enabled:
            expected = 0
        elif value >= th:
            expected, advance = 255, True
        elif count < minimum_count:
            expected, advance = 255, True
        else:
            expected = min(255, max(0, value + margin - th) * multiplier)
        replay.run((start, stop))
        assert m[result] == expected, (early, value, flags, enabled, count, th, ix, minimum_count, m[result], expected)
        assert m[counter] == (min(255, count + 1) if advance else count)
    return len(fixtures)


def build():
    codes = {f: load_code(f) for f in ('early', 'late')}
    results = []
    for entry in json.loads((ROOT / 'analysis/firmware/catalog.json').read_text())['images']:
        raw = (ROOT / entry['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry['sha256']
        image = b'\xff' * entry['base_address'] + raw
        early = entry['code_family'] == 'early'
        replay = Replay(image, codes[entry['code_family']])
        rng = random.Random(660045)
        checks = dict(selector_dispatch=dispatch_cases(replay, early),
                      constant_request_mode=fixed_request_cases(replay, early, rng),
                      forced_gain_requests=forced_gain_cases(replay, early, rng),
                      blend_qualification=blend_cases(replay, early, rng))
        results.append(dict(id=entry['id'], firmware_sha256=entry['sha256'], family=entry['code_family'],
                            stock_mode=image[0x19DE if early else 0x19B8], checks=checks,
                            executed_instructions=len(replay.executed)))
        print(entry['id'], checks, flush=True)
    deps = ['map_models.py', 'test_speed_sources.py', 'test_full_lift.py']
    return dict(result='passed', cases=sum(sum(r['checks'].values()) for r in results), images=results,
                test_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                dependencies={n: hashlib.sha256((ROOT / 'scripts' / n).read_bytes()).hexdigest() for n in deps},
                scope='Byte-checked fuel mode selector dispatch (all 256 byte values), complete mode-1 constant requests, '
                      'mode-2/mode-4 gains through request construction (including early secondary calculation), '
                      'and load/throttle blend qualification. Synthetic calibration/RAM and constant channel-gain cells. '
                      'Does not establish physical timer units, engine operation or simultaneous interrupt scheduling.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    report = build()
    if args.check:
        assert json.loads(REPORT.read_text()) == report, 'stale fuel-mode report'
    else:
        REPORT.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f"Fuel modes: {report['cases']} cases across {len(report['images'])} BINs passed.")
