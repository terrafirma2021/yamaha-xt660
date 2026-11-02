"""Byte-checked replay of the later PWM and position-feedback control paths.

Independent integer models, real calibration bytes and isolated synthetic RAM.
No source BIN writes, peripheral emulation or claim about the attached actuator.
"""
import argparse
from bisect import bisect_right
import hashlib
import itertools
import json
from pathlib import Path

from test_firmware_lookups import load_code, rd, wr
from test_speed_sources import Replay

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'analysis/firmware/late_auxiliary_validation.json'
CURVES = ((0x446A, 0x445E, 0xAB2), (0x448C, 0x4480, 0xAB4),
          (0x44AE, 0x44A2, 0xAB6), (0x44D0, 0x44C4, 0xAB8))


def reset(r):
    r.ram[:] = bytes(0x1800) + r.image[0x1800:]
    r.reg[:] = bytes(64)


def call(r, pc):
    wr(r.ram, 0x1700, 2, 0x17FE)
    r.run((pc, 0x17FE))


def axis_index(axis, value, scratch_low=0):
    if value <= axis[0]:
        return 0
    if value >= axis[-1]:
        return (len(axis) - 1) * 256
    i = bisect_right(axis, value) - 1
    # C122 writes only the high byte of its divisor scratch word. C1C2
    # writes both bytes. For C122 the pre-existing low byte is an input.
    q16 = (value - axis[i]) * 65536 * 256 // ((axis[i + 1] - axis[i]) * 256 + scratch_low)
    return i * 256 + (q16 + 128) // 256


def curve_value(values, index):
    i, f = divmod(index, 256)
    return values[i] if not f else (values[i] * 256 + (values[i + 1] - values[i]) * f) // 256


def surface_value(values, row, col):
    i, rf = divmod(row, 256)
    j, cf = divmod(col, 256)

    def horizontal(k):
        a = values[k][j]
        b = values[k][j + 1] if cf else a
        return (a * 256 + (b - a) * cf + 128) // 256

    a = horizontal(i)
    return a if not rf else (a * 256 + (horizontal(i + 1) - a) * rf + 128) // 256


def coolant_lookups(r):
    count = changed = 0
    for low in (0, 127, 255):
        for value in range(256):
            reset(r)
            m = r.ram
            m[0xE55], m[0x914], m[0xE63] = 0x40, value, low
            expected = []
            for base, axis, out in CURVES:
                knots = list(r.image[axis:axis + 11])
                values = [rd(r.image, base + 2 * i, 2) for i in range(11)]
                index = axis_index(knots, value, low)
                expected.append(curve_value(values, index))
                changed += index != axis_index(knots, value)
            r.run((0x6A5D, 0x6B12))
            actual = [rd(m, out, 2) for _, _, out in CURVES]
            assert actual == expected, (value, low, actual, expected)
            count += 4
    for gate in (0, 0x80, 0xFF):
        reset(r)
        r.ram[0xE55] = gate
        r.ram[0xAB0:0xAD0] = bytes(range(32))
        before = bytes(r.ram)
        for bounds in ((0x6A5D, 0x6B12), (0xE40C, 0xE536), (0xE536, 0xE6E9)):
            r.run(bounds)
            assert r.ram == before
            count += 1
    assert r.image[0x1841] == 0x80
    for gate in (0x40, 0x80):
        reset(r)
        r.ram[0x1841] = gate
        r.run((0x4878, 0x489D))
        registers = tuple(r.ram[a] for a in (0xA0, 0xA1, 0xA3, 0xA5, 0xB4, 0xB5, 0xBC, 0xBD))
        assert registers == ((2, 0, 7, 16, 255, 255, 255, 255) if gate == 0x40 else (0,) * 8)
        count += 1
    reset(r)
    r.ram[0xE55], r.ram[0x8A3] = 0x40, 4
    before = bytes(r.ram)
    r.run((0xE536, 0xE6E9))
    assert r.ram == before
    count += 1
    return count, changed


def state_cases(r):
    count = 0
    for state, demand, hold, speed in itertools.product(
            (0x80, 0x40, 0x20, 0x10, 8), (0, 30, 400, 7000),
            (0, 30, 500, 8000), (199, 200, 299, 300)):
        reset(r)
        m = r.ram
        m[0xE55], m[0xAB0], m[0xE0F], m[0xAC6] = 0x40, state, 3, 3
        for a, v in ((0xAB2, demand), (0xAB4, hold), (0xAB6, 9),
                     (0xABA, demand), (0xABE, demand), (0x920, speed),
                     (0xE2E, 300), (0xE30, 200)):
            wr(m, a, 2, v)
        new, current, suspended = state, demand, demand
        if state == 0x80:
            new = 0x40
        elif state == 0x40:
            new = 0x20 if demand > hold else 0x10 if hold else 0x80
        elif state == 0x20:
            if speed >= 300:
                new, suspended = 8, min(65535, demand * 10)
            elif hold >= demand:
                new = 0x10 if hold else 0x80
        elif state == 0x10:
            if speed >= 300:
                new, suspended = 8, 0
            else:
                current = hold
                if not hold:
                    new = 0x80
        elif speed < 200:
            new = 0x10 if min(65535, hold * 10) >= demand else 0x20
            if new == 0x20:
                current = demand // 10
        r.run((0xE40C, 0xE536))
        assert (m[0xAB0], rd(m, 0xABA, 2), rd(m, 0xABE, 2)) == (new, current, suspended)
        if state == 0x40:
            assert rd(m, 0xAC0, 2) == 9 and rd(m, 0xAC8, 2) == demand
        count += 1
    # Delay saturation, already-latched startup and the independent wait flag.
    for ticks, delay, latched, waiting in itertools.product((0, 3, 255), (0, 3, 255), (0, 16), (0, 16)):
        reset(r)
        m = r.ram
        m[0xE55], m[0xAB0], m[0xAB1] = 0x40, 0x80, latched
        m[0xAC6], m[0xE0F] = ticks, delay
        r.run((0xE40C, 0xE536))
        expected_ticks = ticks if latched else min(255, ticks + 1)
        assert m[0xAC6] == expected_ticks
        assert m[0xAB0] == (0x40 if not latched and expected_ticks > delay else 0x80)
        m[0xAB0], m[0x881] = 0x40, waiting
        wr(m, 0xAB2, 2, 400)
        wr(m, 0xAB4, 2, 30)
        r.run((0xE40C, 0xE536))
        assert m[0xAB0] == (0x40 if waiting else 0x20)
        count += 2
    return count


def demand_cases(r):
    count = 0
    for full_cycle, state, first, demand, step in itertools.product(
            (False, True), (8, 0x20, 0x10), (False, True), (0, 1, 30, 1000, 65535), (1, 3, 50)):
        reset(r)
        m = r.ram
        m[0xE55], m[0xAB0] = 0x40, state
        m[0xCCA] = int(full_cycle)
        m[0xAB1] = 0 if first else 8
        for a, v in ((0xABA, demand), (0xABE, demand), (0xAC8, 123),
                     (0xAC0, step), (0xAB8, step), (0xAB4, 77)):
            wr(m, a, 2, v)
        if state == 8:
            expected = 1230 if first else max(0, demand - (step if full_cycle else step // 2))
            r.run((0xE536, 0xE6E9))
            assert rd(m, 0xABE, 2) == expected
            assert rd(m, 0xABA, 2) == rd(m, 0xABC, 2) == 0
            assert rd(m, 0xBC, 2) == 65535
        else:
            expected = 77 if state == 0x10 else 123 if first else max(0, demand - (step if full_cycle else step // 2))
            r.run((0xE536, 0xE68C))
            assert rd(m, 0xABA, 2) == expected
            assert rd(r.reg, 18, 2) == (720 if full_cycle else 360)
        count += 1
    for full_cycle in (False, True):
        cycle = 24 if full_cycle else 12
        for phase, demand in itertools.product(range(cycle), (0, 1, 49, 50, 51, 400, 949, 950, 951, 1000, 65535)):
            reset(r)
            m = r.ram
            m[0xAB1], m[0xACE] = int(full_cycle), phase
            wr(m, 0xABA, 2, demand)
            wr(m, 0xE2A, 2, 950)
            wr(m, 0xE2C, 2, 50)
            wr(r.reg, 18, 2, 720 if full_cycle else 360)
            applied = 0 if demand == 0 else 1000 if demand > 950 else max(50, demand)
            duration = (1000 - applied) * (720 if full_cycle else 360) // 100
            steps, remainder = divmod(duration, 300)
            end = (phase + steps) % cycle
            gap = end in (11, 23)
            if gap:
                end -= 1
                remainder += 300
            following = (end + 1) % cycle
            if following in (11, 23):
                following = (following + 1) % cycle
            call(r, 0xF050)
            assert (rd(m, 0xABC, 2), rd(m, 0xAC4, 2), rd(m, 0xACA, 2), m[0xACC], m[0xAC7], m[0xACD]) == (
                applied, duration, remainder, steps, end, following)
            assert bool(m[0xAB1] & 2) == gap
            assert rd(m, 0xBC, 2) == (0 if applied >= 1000 else 65535)
            # Fractional PWM delay on the selected crank event.
            wr(m, 0xA38, 2, 1201)
            wr(m, 0xAC2, 2, 777)
            call(r, 0xF12B)
            delay = 777 if applied == 0 else 0 if applied == 1000 else min(65535, 1201 * remainder // 1200)
            if applied not in (0, 1000) and delay == 1:
                delay = 2
            assert rd(m, 0xAC2, 2) == delay
            count += 2
    for period, fraction in itertools.product((1, 1200, 65535), (0, 1, 2, 599, 1201, 65535)):
        reset(r)
        m = r.ram
        wr(m, 0xABC, 2, 400)
        wr(m, 0xA38, 2, period)
        wr(m, 0xACA, 2, fraction)
        expected = min(65535, period * fraction // 1200)
        expected = 2 if expected == 1 else expected
        call(r, 0xF12B)
        assert rd(m, 0xAC2, 2) == rd(m, 0xBC, 2) == expected
        count += 1
    return count


def position_lookups(r):
    count = 0
    rows = [rd(r.image, 0x4504 + i * 2, 2) for i in range(12)]
    cols = [rd(r.image, 0x44EC + i * 2, 2) for i in range(12)]
    assert set(r.image[0x451C:0x45AC]) == {55}
    points = set(itertools.product(rows, cols))
    for axis, other, reverse in ((rows, cols, False), (cols, rows, True)):
        for v in sorted({0, 65535} | {x + delta for x in axis for delta in (-1, 0, 1) if 0 <= x + delta <= 65535}
                        | {(a + b) // 2 for a, b in zip(axis, axis[1:])}):
            for w in (other[0], (other[4] + other[5]) // 2, other[-1]):
                points.add((w, v) if reverse else (v, w))
    for synthetic in (False, True):
        values = [[(i * 29 + j * 17) % 251 if synthetic else 55 for j in range(12)] for i in range(12)]
        for speed, throttle in sorted(points):
            reset(r)
            m = r.ram
            if synthetic:
                m[0x451C:0x45AC] = bytes(v for row in values for v in row)
            wr(m, 0x920, 2, speed)
            wr(m, 0x8F0, 2, throttle)
            ri, ci = axis_index(rows, speed), axis_index(cols, throttle)
            r.run((0x939C, 0x93DE))
            assert (rd(m, 0xD68, 2), rd(m, 0xD6A, 2)) == (ri, ci)
            assert m[0xD5C] == surface_value(values, ri, ci), (speed, throttle, m[0xD5C], ri, ci)
            count += 1
    return count


def target_cases(r):
    count = 0
    for fixed, startup, reached, mode, hold, recovery, override in itertools.product((False, True), repeat=7):
        reset(r)
        m = r.ram
        # Distinct synthetic constants prevent a flat stock map hiding wrong routing.
        m[0x44E8:0x44EC] = bytes((128 if fixed else 0, 31, 47, 63))
        m[0xD59], m[0xD55], m[0x881] = 4 if startup else 0, int(reached), 32 if mode else 0
        m[0xAD0], m[0xACF] = (64 if hold else 0) | (128 if recovery else 0), 4 if override else 0
        m[0xAD8], m[0xD5C], m[0xD5A], m[0xD5B] = 79, 95, 111, 112
        expected = 47 if fixed else 31 if startup and not reached else 63 if mode else None if hold else 79 if recovery or override else 95
        r.run((0x93DE, 0x9427))
        assert (m[0xD5A], m[0xD5B]) == ((111, 112) if expected is None else (expected, expected))
        assert bool(m[0xD59] & 4) == (startup and (fixed or not reached))
        count += 1
    for value in range(256):
        reset(r)
        m = r.ram
        m[0xD5A] = value
        call(r, 0x96EA)
        assert tuple(m[0xD5D:0xD61]) == (min(255, value + 1), max(0, value - 1), min(255, value + 7), max(0, value - 7))
        count += 1
    return count


def recovery_cases(r):
    count = 0
    for flags, ticks, accumulated, target in itertools.product(
            (0, 8, 128, 136), (0, 2, 3, 255), (0, 3, 250, 255), (0, 31, 55, 95, 255)):
        reset(r)
        m = r.ram
        m[0xAD0], m[0xADE], m[0xADB], m[0xAD8], m[0xD5C] = flags, ticks, accumulated, 79, target
        m[0x4127], m[0x412A], m[0x412E], m[0x412F] = 31, 47, 3, 7
        counter, total, selected, newflags = ticks, accumulated, 79, flags
        if flags & 128:
            counter = min(255, counter + 1)
            if counter >= 3:
                counter = 0
                total = min(255, total + 7)
                selected = min(255, (31 if flags & 8 else 47) + total)
                if selected >= target:
                    selected, total, newflags = target, 0, flags & ~128
        r.run((0x8EE9, 0x8F33))
        assert (m[0xADE], m[0xADB], m[0xAD8], m[0xAD0]) == (counter, total, selected, newflags)
        count += 1
    return count


def feedback_cases(r):
    count = 0
    for target, feedback, old in itertools.product((0, 1, 55, 127, 254, 255), range(256), (1, 2, 4)):
        reset(r)
        m = r.ram
        m[0xD5A] = target
        call(r, 0x96EA)
        m[0x8E4], m[0xD56], m[0xD58], m[0xD59], m[0xD67] = feedback, old, 0, 0x20, 0xC0
        m[1] = 0xA5
        status = 2 if feedback > min(255, target + 1) else 4 if feedback < max(0, target - 1) else 1
        wide = int(max(0, target - 7) <= feedback <= min(255, target + 7))
        changed = status != old or status == 1
        inhibited = not changed
        pulse_mask = 0xC0 if wide else 0 if changed else 0xC0
        drive = 0xC0 if status == 1 or inhibited else (0x40 if status == 4 else 0x80) | (pulse_mask if wide else 0)
        call(r, 0xAED0)
        assert (m[0xD55], m[0xD56], m[0xD57], m[0xD58], m[1]) == (status, status, wide, wide, 0x25 | drive)
        count += 1
    # Independently cover both output directions, inhibit and pulse mask values.
    for status, inhibited, wide, pulse, port in itertools.product((1, 2, 4), (0, 32), (0, 1), (0, 192), (0, 37, 255)):
        reset(r)
        m = r.ram
        r.reg[0] = status
        m[0xD59], m[0xD57], m[0xD67], m[1] = inhibited, wide, pulse, port
        r.run((0xAF7B, 0xAFD2))
        drive = 192 if status == 1 or inhibited else (64 if status == 4 else 128) | (pulse if wide else 0)
        assert m[1] == (port & 63) | drive
        count += 1
    for flags, ticks, width in itertools.product((0, 128, 192), range(256), (1, 253, 255)):
        reset(r)
        m = r.ram
        m[0xD59], m[0xD66], m[0xD61], m[0xD67] = flags, ticks, width, 192
        counter, mask, newflags, newwidth = (ticks + 1) % 256, 192, flags, width
        threshold = 30 if not flags & 128 else 6 if flags & 64 else width
        if counter >= threshold:
            counter = 0
            if not flags & 128:
                mask, newflags = 0, flags | 128
            elif not flags & 64:
                mask, newflags, newwidth = 192, flags | 64, min(255, width + 2)
            else:
                mask, newflags = 0, flags & ~64
        call(r, 0xAFD3)
        assert (m[0xD66], m[0xD67], m[0xD59], m[0xD61]) == (counter, mask, newflags, newwidth)
        count += 1
    return count


def build():
    code = load_code('late')
    results = []
    for entry in json.loads((ROOT / 'analysis/firmware/catalog.json').read_text())['images']:
        if entry['code_family'] != 'late':
            continue
        raw = (ROOT / entry['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry['sha256']
        r = Replay(b'\xff' * entry['base_address'] + raw, code)
        lookups, scratch_sensitive = coolant_lookups(r)
        checks = dict(coolant_lookup_and_gates=lookups, pwm_state_transitions=state_cases(r),
                      pwm_demand_and_phase=demand_cases(r), position_lookup=position_lookups(r),
                      position_target_and_bounds=target_cases(r), recovery_target=recovery_cases(r),
                      feedback_and_output=feedback_cases(r))
        assert hashlib.sha256((ROOT / entry['file']).read_bytes()).hexdigest() == entry['sha256']
        results.append(dict(id=entry['id'], firmware_sha256=entry['sha256'], checks=checks,
                            instructions_byte_checked=len(r.executed), stock_pwm_gate=128, required_pwm_gate=64,
                            stock_position_values=[55], scratch_sensitive_index_cases=scratch_sensitive))
        print(entry['id'], checks, flush=True)
    return dict(result='passed', images=results, cases=sum(sum(x['checks'].values()) for x in results),
                test_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                dependencies={name: hashlib.sha256((ROOT / 'scripts' / name).read_bytes()).hexdigest()
                              for name in ('test_speed_sources.py', 'test_firmware_lookups.py', 'test_full_lift.py')},
                scope='Four later BINs: coolant interpolation and stock-disabled gates, PWM state transitions, '
                      'demand decay and crank-phase scheduling, position lookup, overrides and recovery ramp, deadbands, '
                      'feedback direction and paired PORTB outputs. Synthetic RAM fixtures also expose '
                      'C122 divisor scratch dependence and flat-map routing. No source BIN changes; '
                      'not a full running-engine/peripheral simulation or identification of the attached actuator.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    report = build()
    if args.check:
        assert json.loads(REPORT.read_text()) == report, 'stale later auxiliary-control report'
    else:
        REPORT.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f"Later auxiliary controls: {report['cases']} checks passed.")
