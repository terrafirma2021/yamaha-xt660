"""Independent mode-state model versus original later CPU12 instructions.

Checks entry/exit, shared ignition/fuel/position recovery, output timeout, and
ADC feedback encoding. Synthetic RAM and calibration fixtures; no BIN writes.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import random

from test_firmware_lookups import load_code, rd, wr
from test_speed_sources import Replay

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'analysis/firmware/late_mode_validation.json'
FIELDS = dict(flags=0xACF, lanes=0xAD0, first_ticks=0xAD4, second_ticks=0xAD5,
              ignition=0xAD6, fuel=0xAD7, position=0xAD8, ignition_step=0xAD9,
              fuel_step=0xADA, position_step=0xADB, ignition_ticks=0xADC,
              fuel_ticks=0xADD, position_ticks=0xADE)
CONFIG = dict(window_low=0x411B, window_high=0x411C, first_ratio=0x411D,
              second_ratio=0x411E, dwell=0x411F, trigger=0x4120, confirm_time=0x4121,
              confirm=0x4122, first_ignition=0x4125, first_fuel=0x4126,
              first_position=0x4127, second_ignition=0x4128, second_fuel=0x4129,
              second_position=0x412A, active_time=0x412B, recovery_period=0x412C,
              fuel_increment=0x412D, position_period=0x412E, position_increment=0x412F)


def sat(n):
    return min(255, n)


def model(state, cfg, *, tick, road, ratio, throttle, ignition_map, position_map):
    """One shared-mode service call, expressed in phase/target operations."""
    s = dict(state)
    f, lane = s['flags'], s['lanes']
    if tick % 2 == 0:
        s['first_ticks'] = sat(s['first_ticks'] + 1)
        s['second_ticks'] = sat(s['second_ticks'] + 1)
    if cfg['window_low'] < road < cfg['window_high']:
        f |= 128
    else:
        f &= ~128
        if f & 64:
            f &= ~(64 | 32 | 16)
            lane &= ~(8 | 4 | 64)
            s['first_ticks'] = s['second_ticks'] = 0

    if not f & (8 | 4 | 2):
        aborted = False
        for prefix, flag, lane_flag in (('first', 32, 8), ('second', 16, 4)):
            if ratio == cfg[prefix + '_ratio']:
                if s[prefix + '_ticks'] >= cfg['dwell']:
                    f |= flag
                    lane |= lane_flag | 64
            else:
                s[prefix + '_ticks'] = 0
                if f & flag:
                    f = (f & ~(flag | 64)) | 2
                    lane &= ~lane_flag
                    aborted = True
                    break
        if not aborted:
            f |= 64
            if throttle >= cfg['trigger']:
                s['first_ticks'] = s['second_ticks'] = 0
                if f & (32 | 16):
                    f = (f | 8) & ~(64 | 32 | 16)

    if f & 8:
        if s['first_ticks'] >= cfg['confirm_time']:
            f = (f | 2) & ~(64 | 32 | 16 | 8)
            s['first_ticks'] = s['second_ticks'] = 0
        elif throttle >= cfg['confirm']:
            s['first_ticks'] = 0
            f = (f | 4) & ~8

    prefix = 'first' if lane & 8 else 'second'
    if f & 4:
        for target in ('ignition', 'fuel', 'position'):
            s[target] = cfg[prefix + '_' + target]
        lane &= ~64
        if throttle < cfg['confirm'] or s['first_ticks'] >= cfg['active_time']:
            f = (f | 2 | 1) & ~4
            lane |= 2 | 128 | 32

    if f & 2:
        if f & 1:
            s['ignition_ticks'] = sat(s['ignition_ticks'] + 1)
            if s['ignition_ticks'] >= cfg['recovery_period']:
                s['ignition_ticks'] = 0
                s['ignition_step'] = sat(s['ignition_step'] + 1)
                if lane & 2:
                    value = sat(cfg[prefix + '_ignition'] + s['ignition_step'])
                    if value < ignition_map:
                        s['ignition'] = value
                    else:
                        lane &= ~2
                if not lane & 2:
                    f &= ~1
                    s['ignition_step'] = 0
        if lane & 128:
            s['position_ticks'] = sat(s['position_ticks'] + 1)
            if s['position_ticks'] >= cfg['position_period']:
                s['position_ticks'] = 0
                s['position_step'] = sat(s['position_step'] + cfg['position_increment'])
                value = sat(cfg[prefix + '_position'] + s['position_step'])
                if value >= position_map:
                    value = position_map
                    lane &= ~128
                    s['position_step'] = 0
                s['position'] = value
        if lane & 32:
            s['fuel_ticks'] = sat(s['fuel_ticks'] + 1)
            if s['fuel_ticks'] >= cfg['recovery_period']:
                s['fuel_ticks'] = 0
                s['fuel_step'] = sat(s['fuel_step'] + cfg['fuel_increment'])
                base = cfg[prefix + '_fuel']
                value = min(128, base + s['fuel_step']) if base < 128 else max(128, base - s['fuel_step'])
                if value == 128:
                    lane &= ~32
                    s['fuel_step'] = 0
                s['fuel'] = value
        if not lane & 128:
            lane &= ~64
            if not lane & 32 and not f & 1:
                f &= ~2
                s['first_ticks'] = s['second_ticks'] = 0
                lane &= ~(8 | 4)
    s['flags'], s['lanes'] = f, lane
    return s


def reset(r):
    r.ram[:] = bytes(0x1800) + r.image[0x1800:]
    r.reg[:] = bytes(64)


def step(r, expected, cfg, tick=0, road=47, ratio=3, throttle=0, ignition_map=115, position_map=55):
    inputs = dict(tick=tick, road=road, ratio=ratio, throttle=throttle,
                  ignition_map=ignition_map, position_map=position_map)
    m = r.ram
    for key, value in inputs.items():
        m[dict(tick=0xB29, road=0xAEE, ratio=0x89A, throttle=0x8F2, ignition_map=0xA8D, position_map=0xD5C)[key]] = value
    expected = model(expected, cfg, **inputs)
    r.run((0x8CF6, 0x8FAD))
    actual = {k: m[a] for k, a in FIELDS.items()}
    assert actual == expected, (inputs, {k: (actual[k], expected[k]) for k in expected if actual[k] != expected[k]})
    return expected


def fixture(r, state=None, config=None):
    reset(r)
    s = {k: 0 for k in FIELDS}
    s.update(state or {})
    cfg = {k: r.image[a] for k, a in CONFIG.items()}
    cfg.update(config or {})
    for k, a in FIELDS.items():
        r.ram[a] = s[k]
    for k, a in CONFIG.items():
        r.ram[a] = cfg[k]
    return s, cfg


def boundary_cases(r):
    count = 0
    phases = ((0, 0), (64 | 32, 8 | 64), (64 | 16, 4 | 64), (8, 8 | 64),
              (4, 8), (2 | 1, 8 | 2 | 32 | 128), (2, 4 | 32), (2, 8 | 128))
    for phase, ticks, road, ratio, throttle in itertools.product(
            phases, (0, 19, 20, 99, 100, 129, 130, 255), (42, 43, 44, 51, 52), (3, 255), (60, 61, 153, 154)):
        s, cfg = fixture(r, dict(flags=phase[0], lanes=phase[1], first_ticks=ticks, second_ticks=ticks))
        step(r, s, cfg, tick=count % 2, road=road, ratio=ratio, throttle=throttle)
        count += 1
    rng = random.Random(660)
    for _ in range(512):
        phase = rng.choice(phases)
        s = {k: rng.randrange(256) for k in FIELDS}
        s.update(flags=phase[0], lanes=phase[1])
        cfg = {k: rng.choice((0, 1, 127, 128, 254, 255)) for k in CONFIG}
        s, cfg = fixture(r, s, cfg)
        step(r, s, cfg, tick=rng.randrange(256), road=rng.randrange(256), ratio=rng.randrange(256),
             throttle=rng.randrange(256), ignition_map=rng.randrange(256), position_map=rng.randrange(256))
        count += 1
    return count


def sequences(r):
    count = 0
    records = []
    for label, cfg_override, road, ratio, confirm, sustain in (
        ('stored first lane: complete recovery', {}, 47, 3, True, False),
        ('stored first lane: maximum duration', {}, 47, 3, True, True),
        ('confirmation timeout', {}, 47, 3, False, False),
        ('outside road window', {}, 43, 3, True, False),
        ('unselected ratio', {}, 47, 2, True, False),
        ('synthetic second lane', dict(second_ratio=4, second_position=31, second_fuel=192), 47, 4, True, False)):
        s, cfg = fixture(r, config=cfg_override)
        seen, positions, ignitions, first_active, first_recovery = set(), set(), set(), None, None
        for n in range(900):
            throttle = 0 if n < 210 else 61 if n < 214 or not confirm else 154 if n < (550 if sustain else 225) else 0
            s = step(r, s, cfg, tick=n % 256, road=road, ratio=ratio, throttle=throttle)
            if s['flags'] & 4:
                first_active = n if first_active is None else first_active
            if s['flags'] & 2:
                first_recovery = n if first_recovery is None else first_recovery
            seen.add(s['flags'] & 15)
            r.ram[0xD59] = 0
            # Same caller's target selector and normal ignition consumer.
            r.run((0x93DE, 0x9427))
            positions.add(r.ram[0xD5A])
            r.ram[0xA8E], r.ram[0xD1E] = 128, 0
            r.run((0x7DA7, 0x7DE5))
            wanted = s['ignition'] if (s['flags'] & 4 or s['lanes'] & 2) else min(115, r.image[0x3865])
            assert r.ram[0xA8C] == wanted
            ignitions.add(wanted)
            if label != 'synthetic second lane' and r.ram[0xD5A] == 0:
                # Before any target is selected, hold retains startup's target.
                raise AssertionError('target was held before initialization')
            count += 1
        expected_active = label in ('stored first lane: complete recovery', 'stored first lane: maximum duration', 'synthetic second lane')
        assert (first_active is not None) == expected_active
        assert not s['flags'] & (4 | 2 | 1)
        if label != 'synthetic second lane':
            assert positions == {55}
        records.append(dict(name=label, first_active_call=first_active, first_recovery_call=first_recovery,
                            selected_position_values=sorted(positions), normal_ignition_values=sorted(ignitions)))
    return count, records


def inhibit_model(flags, ticks, attempts, retries, periods, first_pause, long_pause):
    ticks = sat(ticks + 1)
    if not flags & (16 | 8) and ticks >= first_pause:
        ticks = 0
        flags |= 32
        attempts = sat(attempts + 1)
        if attempts == 1:
            flags |= 16
        elif long_pause:
            retries = sat(retries + 1)
            flags |= 8
        else:
            periods, attempts = 0, 0
            flags &= ~(32 | 8)
            return flags, ticks, attempts, retries, periods
    if flags & 16:
        if ticks >= 25:
            ticks = 0
            flags &= ~(32 | 16)
    elif flags & 8 and ticks >= 25:
        ticks = 0
        periods = sat(periods + 1)
        if periods >= long_pause:
            periods, attempts = 0, 0
            flags &= ~(32 | 8)
    return flags, ticks, attempts, retries, periods


def inhibit_cases(r):
    count = 0
    for flags, ticks, attempts, periods, limit in itertools.product((0, 32 | 16, 32 | 8), (0, 24, 25, 49, 50, 255), (0, 1, 255), (0, 99, 255), (0, 100)):
        reset(r)
        m = r.ram
        m[0x45B4] = limit
        m[0xD59], m[0xD64], m[0xD62], m[0xD63], m[0xD65] = flags, ticks, attempts, 7, periods
        expected = inhibit_model(flags, ticks, attempts, 7, periods, 50, limit)
        r.run((0xA837, 0xA8BD))
        assert tuple(m[a] for a in (0xD59, 0xD64, 0xD62, 0xD63, 0xD65)) == expected
        count += 1
    return count


def electrical_and_scheduler(r):
    count = 0
    for value in range(1024):
        reset(r)
        wr(r.reg, 0, 2, value << 6)
        r.run((0x6B29, 0x6B35))
        assert r.ram[0x8E4] == value // 4
        wr(r.ram, 0x1700, 2, 0x17FE)
        r.run((0x5F95, 0x17FE))
        assert r.ram[0xD59] & 4 and r.ram[0xD5A] == 55
        wr(r.ram, 0x1700, 2, 0x17FE)
        r.run((0xAED0, 0x17FE))
        r.ram[0xD5C] = 99
        r.run((0x93DE, 0x9427))
        reached = 216 <= value <= 227
        assert r.ram[0xD5A] == (99 if reached else 55)
        assert bool(r.ram[0xD59] & 4) != reached
        count += 1
    for tick in range(256):
        reset(r)
        r.ram[0xB29] = tick
        r.run((0x5FF6, 0x6001))
        assert bool(r.ram[0x882] & 4) == (tick % 2 == 0)
        r.run((0x603C, 0x6051))
        assert bool(r.ram[0x882] & 32) == (tick % 8 == 2)
        count += 2
    for sync, period, phase, mode in itertools.product((0, 128), range(256), (0, 1, 11), (0, 1)):
        reset(r)
        m = r.ram
        m[0xC20], m[0xA38], m[0xC26], m[0x942], m[0xCCA] = sync, period, phase, phase, mode
        m[0x881], m[0x880], m[0xDD9], m[0xDDA] = 32, 1, 40, 80
        r.run((0xD814, 0xD862))
        assert bool(m[0x881] & 32) != bool(sync)
        count += 1
    return count


def build():
    code = load_code('late')
    results = []
    for e in json.loads((ROOT / 'analysis/firmware/catalog.json').read_text())['images']:
        if e['code_family'] != 'late':
            continue
        raw = (ROOT / e['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == e['sha256']
        r = Replay(b'\xff' * e['base_address'] + raw, code)
        boundaries = boundary_cases(r)
        sequence_count, paths = sequences(r)
        checks = dict(mode_boundaries=boundaries, mode_sequence_calls=sequence_count,
                      output_inhibit=inhibit_cases(r), adc_and_scheduler=electrical_and_scheduler(r))
        assert hashlib.sha256((ROOT / e['file']).read_bytes()).hexdigest() == e['sha256']
        results.append(dict(id=e['id'], firmware_sha256=e['sha256'], checks=checks,
                            instructions_byte_checked=len(r.executed), scenarios=paths,
                            stored_configuration={k: r.image[a] for k, a in CONFIG.items()},
                            ignition_override_enabled=r.image[0x4123] == 128,
                            extra_fuel_gain_enabled=r.image[0x4124] == 128))
        print(e['id'], checks, flush=True)
    return dict(result='passed', cases=sum(sum(x['checks'].values()) for x in results), images=results,
                test_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                dependencies={n: hashlib.sha256((ROOT / 'scripts' / n).read_bytes()).hexdigest()
                              for n in ('test_speed_sources.py', 'test_firmware_lookups.py', 'test_full_lift.py')},
                scope='Complete 8CF6..8FAD mode-state block and its normal-ignition/position consumers, '
                      'output timeout/retry, ADC7 high-byte encoding, startup-target release, '
                      'valid-crank release of the stopped-state flag, and scheduler divider. '
                      'Synthetic RAM is not a physical engine, PCB routing, sensor calibration, or absolute timing test.')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--check', action='store_true')
    args = p.parse_args()
    result = build()
    if args.check:
        assert json.loads(REPORT.read_text()) == result, 'stale later mode evidence'
    else:
        REPORT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f"Later mode triggers: {result['cases']} checks passed.")
