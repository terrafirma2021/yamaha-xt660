"""Check both base-map display profiles against byte-checked CPU12 replay.

Stored cells and interpolation feed the original selectors, rounding and normal/
alternate consumers. Synthetic RAM isolates the software path; these fixtures do
not establish a physical TDC origin or emulate a running engine. BINs stay intact.
"""
import argparse
import hashlib
import json
from pathlib import Path

from ignition_profiles import estimated_ignition
from spark_models import fire_plan
from test_firmware_lookups import load_code, rd, wr
from test_speed_sources import Replay, LAYOUTS as PLANNERS

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'analysis/firmware/ignition_display_validation.json'
# Independent instruction anchors and expected map coverage, not imported from
# the display allowlist: omission or accidental expansion must fail this test.
PATHS = {
    'early': dict(maps=('main_u8_A', 'main_u8_B', 'main_u8_C', 'correction_surface_D'),
                  bases=(0x42AE, 0x452E, 0x47AE, 0x4A60), scratch=0xDDE,
                  select=(0x8885, 0x88A8), lookup=(0x88A8, 0x88B1), base=0xA83,
                  alternate=(0xB884, 0xB892), alternate_base=0xA88,
                  normal_consumer=(0x8A19, 0x8A89), alternate_consumer=(0x899E, 0x8A89),
                  gain=0xA86, bound=0xD05, cap=0x4242, final=0xA82,
                  ratio=0x898, split=0x4245),
    'late': dict(maps=('table_38d2', 'table_3b52', 'table_3dd2', 'table_4084'),
                 bases=(0x38D2, 0x3B52, 0x3DD2, 0x4084), scratch=0xE62,
                 select=(0x7C4A, 0x7C66), lookup=(0x7C66, 0x7C6F), base=0xA8D,
                 alternate=(0xB098, 0xB0A6), alternate_base=0xA90,
                 normal_consumer=(0x7DA7, 0x7DF3), alternate_consumer=(0x7D50, 0x7DF3),
                 gain=0xA8E, bound=0xD1E, cap=0x3865, final=0xA8C,
                 ratio=0x89A, split=0x3868),
}


def reset(replay):
    replay.ram[:] = bytes(0x1800) + replay.image[0x1800:]
    replay.reg[:] = bytes(64)


def interpolated(values, row, col):
    r, rf = divmod(row, 256)
    c, cf = divmod(col, 256)

    def horizontal(index):
        a = values[index][c]
        b = values[index][c + 1] if cf else a
        return (a * 256 + (b - a) * cf + 128) // 256

    a = horizontal(r)
    return a if not rf else (a * 256 + (horizontal(r + 1) - a) * rf + 128) // 256


def sample(replay, path, family, index, row, col):
    reset(replay)
    m = replay.ram
    wr(m, path['scratch'], 2, row)
    wr(m, path['scratch'] + 2, 2, col)
    if index < 3:
        if family == 'early':
            m[0xD87], m[0x896] = 9, (0 if index == 0 else 16)
        else:
            m[0x88F] = 128 if index == 0 else 0
        m[path['ratio']] = m[path['split']] + (index == 2)
        replay.run(path['select'])
        assert rd(replay.reg, 16, 2) == path['bases'][index] - 3
        replay.run(path['lookup'])
        return m[path['base']]
    replay.run(path['alternate'])
    return m[path['alternate_base']]


def consume(replay, path, alternate, value, gain=128, bound=0):
    m = replay.ram
    m[path['alternate_base'] if alternate else path['base']] = value
    m[path['gain']], m[path['bound']] = gain, bound
    replay.run(path['alternate_consumer'] if alternate else path['normal_consumer'])
    expected = min(max(value, bound) * gain // 128, m[path['cap']])
    assert m[path['final']] == expected
    return expected


def plan(replay, family, value):
    l = PLANNERS[family]
    pitch = (513, 1600, 5000)[value % 3]
    correction = (0, 150, 255)[value % 3]
    for key, v in [('pitch', pitch), ('three', 3 * pitch),
                   ('quarter', 3 * pitch // 4), ('minimum', 10)]:
        wr(replay.ram, l[key], 2, v)
    replay.ram[l['correction']] = correction
    replay.reg[0] = value
    replay.run(l['planner'])
    offset = rd(replay.image, l['offset'], 2)
    actual = (replay.ram[l['event']], rd(replay.ram, l['advance'], 2),
              rd(replay.ram, l['residual'], 2))
    assert actual == fire_plan(value, pitch * 3, pitch * 3 // 4, pitch, correction, 10, offset)


def build():
    codes = {f: load_code(f) for f in PATHS}
    decoded = {x['id']: x for x in json.loads((ROOT / 'analysis/firmware/decode_catalog.json').read_text())['images']}
    results = []
    for entry in json.loads((ROOT / 'analysis/firmware/catalog.json').read_text())['images']:
        raw = (ROOT / entry['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry['sha256']
        family = entry['code_family']
        p = PATHS[family]
        maps = json.loads((ROOT / decoded[entry['id']]['maps_path']).read_text())
        selected = [m for m in maps if estimated_ignition(m, family)]
        assert {m['id'] for m in selected} == set(p['maps'])
        by_id = {m['id']: m for m in selected}
        replay = Replay(b'\xff' * entry['base_address'] + raw, codes[family])
        checks = dict(stored_cells=0, interpolated_points=0, consumer_and_planner=0, profile_guards=0)
        map_results = []
        for index, map_id in enumerate(p['maps']):
            m = by_id[map_id]
            assert int(m['data_address'], 16) == p['bases'][index]
            profile = estimated_ignition(m, family)
            assert profile['hardware_verified'] is False
            assert (profile['slope'], profile['offset'], profile['trigger_reference_btdc']) == (90 / 256, -12.5, 10)
            for other in ('unknown', 'late' if family == 'early' else 'early'):
                assert estimated_ignition(m, other) is None
                checks['profile_guards'] += 1
            for key, value in [('id', 'fuel'), ('data_address', '0x0000'),
                               ('rows', m['rows'] + 1), ('columns', m['columns'] + 1), ('element_bytes', 2)]:
                assert estimated_ignition(dict(m, **{key: value}), family) is None
                checks['profile_guards'] += 1
            values = m['raw_values']
            for r, row in enumerate(values):
                for c, value in enumerate(row):
                    assert replay.image[p['bases'][index] + r * m['columns'] + c] == value
                    actual = sample(replay, p, family, index, r * 256, c * 256)
                    assert actual == value, (entry['id'], map_id, r, c, actual, value)
                    consume(replay, p, index == 3, actual)
                    checks['stored_cells'] += 1
            for r in (0, m['rows'] // 2, m['rows'] - 2):
                for c in (0, m['columns'] // 2, m['columns'] - 2):
                    for rf, cf in ((0, 127), (1, 255), (128, 128), (255, 1)):
                        actual = sample(replay, p, family, index, r * 256 + rf, c * 256 + cf)
                        assert actual == interpolated(values, r * 256 + rf, c * 256 + cf)
                        checks['interpolated_points'] += 1
            map_results.append(dict(id=map_id, address=m['data_address'], cells=m['rows'] * m['columns'],
                                    profile=profile['id']))
        # Isolate corrections instead of pretending a displayed base is final spark.
        for alternate in (False, True):
            for value in range(256):
                for gain, bound in ((128, 0), (64, 100), (192, 0), (128, 255)):
                    reset(replay)
                    final = consume(replay, p, alternate, value, gain, bound)
                    plan(replay, family, final)
                    checks['consumer_and_planner'] += 1
        assert hashlib.sha256((ROOT / entry['file']).read_bytes()).hexdigest() == entry['sha256']
        results.append(dict(id=entry['id'], family=family, firmware_sha256=entry['sha256'], maps=map_results,
                            checks=checks, instructions_byte_checked=len(replay.executed)))
        print(entry['id'], checks, flush=True)
    dependencies = ['ignition_profiles.py', 'test_firmware_lookups.py', 'test_speed_sources.py',
                    'test_full_lift.py', 'spark_models.py']
    return dict(result='passed', images=results,
                cases=sum(sum(x['checks'].values()) for x in results),
                test_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                dependencies={n: hashlib.sha256((ROOT / 'scripts' / n).read_bytes()).hexdigest() for n in dependencies},
                scope='Both code families, all registered BINs: every base-map knot, selected fractional '
                      'lookups, map selection, normal/alternate consumers and final planner under isolated '
                      'synthetic RAM conditions. No BIN writes. This does not establish a physical TDC '
                      'reference, every live correction/mode or actual spark timing.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    report = build()
    if args.check:
        assert json.loads(REPORT.read_text()) == report, 'stale ignition-display report'
    else:
        REPORT.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f"Ignition display: {report['cases']} checks across {len(report['images'])} BINs passed.")
