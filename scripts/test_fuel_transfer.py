"""Replay ordinary fuel corrections through the injector request in both families.

Lookup results and already-normalized base quantities are injected. All executed
instructions are byte-checked against each BIN; this is not a complete ECU run.
"""
import argparse
import hashlib
import json
import random
from pathlib import Path

from map_models import normal_gains, pre_gain, primary_request, q8, rounded_q8, clamp
from test_speed_sources import Replay
from test_firmware_lookups import load_code, rd, wr

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'analysis/firmware/fuel_transfer_validation.json'


def build():
    codes = {f: load_code(f) for f in ('early', 'late')}
    results = []
    for entry in json.loads((ROOT / 'analysis/firmware/catalog.json').read_text())['images']:
        raw = (ROOT / entry['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry['sha256']
        image = b'\xff' * entry['base_address'] + raw
        early = entry['code_family'] == 'early'
        replay = Replay(image, codes[entry['code_family']])
        rng = random.Random(660042)
        unity = None
        for n in range(768):
            replay.ram[:] = bytes(0x1800) + image[0x1800:]
            replay.reg[:] = bytes(64)
            m = replay.ram
            # First case is the independently specified unity reference. The
            # remainder stress integer wrapping, rounding and saturation.
            post, transient, adaptive = [rng.randrange(65536) for _ in range(3)]
            ca, cb, centered, iat, response, pa, pb = [rng.randrange(256) for _ in range(7)]
            if n == 0:
                post = ca = cb = 0
                transient = adaptive = 32768
                centered = iat = response = pa = pb = 128
            for a, v in [(0x992 if early else 0x990, post),
                         (0x982 if early else 0x980, transient),
                         (0x97E if early else 0x97C, adaptive)]:
                wr(m, a, 2, v)
            for a, v in [(0x97B, ca), (0x980 if early else 0x97E, centered),
                         (0x979, iat), (0x97A, response), (0x970, pa), (0x978, pb)]:
                m[a] = v
            if early:
                m[0x97C] = cb
                expected = normal_gains(post, ca, cb, centered, transient, adaptive, iat, response, pa, pb)
                replay.run((0x8220, 0x82F0))
                ga, gb = expected[0x960], expected[0x964]
            else:
                pre = pre_gain(post >> 8, ca, centered, transient, adaptive)
                corrected = q8(q8(pre, iat + 384) >> 1, response)
                ga, gb = q8(corrected, pa), q8(corrected, pb)
                expected = {0x96E: pre, 0x96C: corrected, 0x968: ga, 0x96A: gb}
                replay.run((0x77F8, 0x785F))
            for a, value in expected.items():
                assert rd(m, a, 2) == value, (entry['id'], n, hex(a))
            if n == 0:
                assert ga == gb == 256
                unity = {'load_gain_Q8': ga, 'throttle_gain_Q8': gb}
            qa, qb, compensation = [rng.randrange(65536) for _ in range(3)]
            additive, blend, global_byte = [rng.randrange(256) for _ in range(3)]
            lower, upper = sorted(rng.sample(range(65536), 2))
            mode = n % 2
            if n % 4 == 0:
                lower = rd(image, 0x19DA if early else 0x19B4, 2)
                upper = rd(image, 0x19DC if early else 0x19B6, 2)
                global_byte = image[0x19D4 if early else 0x19AE]
            for a, value in [(0xCE4 if early else 0xCFE, qa),
                             (0xCE8 if early else 0xD00, qb),
                             (0x95E if early else 0x966, compensation),
                             (0x19DA if early else 0x19B4, lower),
                             (0x19DC if early else 0x19B6, upper)]:
                wr(m, a, 2, value)
            m[0x95C if early else 0x964] = additive
            m[0x998 if early else 0x996] = blend
            m[0x19D4 if early else 0x19AE] = global_byte
            m[0xCA8 if early else 0xCCA] = mode
            if early:
                reduction = (0, 1, 1023, 1024, 1025, 65535)[n % 6]
                wr(m, 0xAD4, 2, reduction)
                expected = primary_request(qa, qb, ga, gb, additive, blend, reduction,
                                           lower, upper, global_byte, mode, compensation)
                replay.run((0x8323, 0x842B))
            else:
                a = q8(clamp(qa + 4 * (additive - 128)), ga)
                b = q8(clamp(qb + 4 * (additive - 128)), gb)
                limited = clamp(b * blend // 256 + a * (255 - blend) // 256, lower, upper)
                # Exercise the extra late-family post-blend gate, including its
                # stock-disabled setting, without assigning a hardware role.
                m[0x4124] = (255, 128, 0)[(n // 2) % 3]
                m[0xACF] = 4 if (n // 6) % 2 else 0
                m[0xAD0] = 32 if (n // 12) % 2 else 0
                m[0xAD7] = rng.randrange(256)
                if not mode:
                    scaled = rounded_q8(limited, global_byte * 4)
                elif m[0x4124] == 128 and (m[0xACF] & 4 or m[0xAD0] & 32):
                    scaled = rounded_q8(limited, m[0xAD7] * 2)
                else:
                    scaled = limited
                final = clamp(scaled + compensation)
                expected = {0x95C: a, 0x95E: b, 0x95A: limited, 0x956: limited,
                            0x958: scaled, 0x954: final, 0x948: final}
                replay.run((0x7885, 0x79A0))
            for a, value in expected.items():
                assert rd(m, a, 2) == value, (entry['id'], n, hex(a), rd(m, a, 2), value)
        results.append(dict(id=entry['id'], firmware_sha256=entry['sha256'], family=entry['code_family'],
                            gain_and_request_cases=768, executed_instructions=len(replay.executed),
                            unity_reference=unity,
                            stock_post_blend_enable=None if early else image[0x4124]))
    return dict(result='passed', cases=sum(r['gain_and_request_cases'] for r in results), images=results,
                test_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                model_script_sha256=hashlib.sha256((ROOT / 'scripts/map_models.py').read_bytes()).hexdigest(),
                replay_script_sha256=hashlib.sha256((ROOT / 'scripts/test_speed_sources.py').read_bytes()).hexdigest(),
                interpreter_sha256=hashlib.sha256((ROOT / 'scripts/test_full_lift.py').read_bytes()).hexdigest(),
                scope='Byte-checked normal correction gain and primary injector-request blocks in all nine BINs. '
                      'Injected lookup results/normalized base quantities; integer edges and stock/synthetic gates. '
                      'No physical units, upstream map/mode selection, secondary injection, peripheral scheduling '
                      'or on-engine validation are established by these fixtures.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    report = build()
    if args.check:
        assert json.loads(REPORT.read_text()) == report, 'stale fuel-transfer report'
    else:
        REPORT.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f"Fuel transfer: {report['cases']} checks, {len(report['images'])} BINs passed.")
