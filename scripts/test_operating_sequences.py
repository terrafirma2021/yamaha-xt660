"""Byte-checked operating sequences, with explicitly simulated timer pin states.

The interpreter has no analog hardware or autonomous timer. These fixtures join
real caller, lookup and output instructions, and compare independent arithmetic
and state expectations. Synthetic calibration is memory-only, never saved BINs.
"""
import argparse
import hashlib
import json
from pathlib import Path

from map_models import clamp, decay, extra_transient_ticks
from test_firmware_lookups import load_code, rd, wr, reference
from test_input_coordinates import reset
from test_pressure_sources import lookup
from test_speed_sources import Replay
from spark_models import fire_plan, charge_plan

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT/'analysis/firmware/operating_sequence_validation.json'


class Sequence(Replay):
    def run(self, bounds):
        pc, stop = bounds
        stack = getattr(self, 'stack', 0x1700)
        wr(self.reg, 42, 2, stack)
        wr(self.ram, stack, 2, 0x17FE)
        self.trace = []
        for _ in range(20000):
            if pc == stop:
                return
            hook = getattr(self, 'before_instruction', None)
            if hook: hook(pc, len(self.trace))
            row = self.code[pc]
            raw = bytes.fromhex(row['bytes'])
            assert self.image[pc:pc+len(raw)] == raw, hex(pc)
            self.executed.add(pc)
            self.trace.append(pc)
            status, pc = reference(row, self.ram, self.reg)
            assert status == 0
        raise AssertionError(('sequence bound', hex(pc)))

    def call(self, pc):
        self.run((pc, 0x17FE))


def uniform_q8(m, base, value):
    position = clamp(value-m[base], 0, m[base+1])*m[base+2]
    i, f = divmod(position, 256)
    a = m[base+3+i]
    return a*256 if not f else a*256+(m[base+4+i]-a)*f


def post_start(r, family='early'):
    early = family == 'early'
    coolant = 0x8F4 if early else 0x914
    config = 0x32EE if early else 0xDA0
    states = (0x994, 0x996) if early else (0x992, 0x994)
    curves = (0x32EF, 0x3301) if early else (0xDA1, 0xDB3)
    rates = (0x3313, 0x3314) if early else (0x32ED, 0x32EE)
    entry = (0x715A, 0x7190) if early else (0x69E8, 0x6A1E)
    update = (0x7FD8, 0x800C) if early else (0x765A, 0x768E)
    combined = 0x992 if early else 0x990
    cases = 0
    for temperature in (0, 1, 79, 80, 127, 128, 144, 159, 200, 254, 255):
        for flags in range(4):
            for reload in (False, True):
                m = reset(r)
                if not early:
                    m[0xDA1:0xDC5] = m[0x32C9:0x32ED]
                m[coolant] = temperature
                m[0x883], m[0x884] = (32 if flags&1 else 0), (8 if flags&2 else 0)
                m[config] = 0 if reload else 128
                wr(m, states[0], 2, 12345); wr(m, states[1], 2, 23457)
                pair = tuple(uniform_q8(m, a, temperature) for a in curves)
                expected = pair if flags == 0 else (12345, 23457)
                r.run(entry)
                assert tuple(rd(m, a, 2) for a in states) == expected
                # Changing coolant on the next call cannot bypass the one-shot.
                m[coolant] = 255-temperature
                r.run(entry)
                assert tuple(rd(m, a, 2) for a in states) == expected
                r.call(0x721F if early else 0xF3A8)
                pair = tuple(uniform_q8(m, a, m[coolant]) for a in curves)
                if reload: expected = pair
                assert tuple(rd(m, a, 2) for a in states) == expected
                assert not m[0x883]&32
                # Reset clears the outer gate, but not the inner gate.
                old_inner = m[0x884]&8
                r.run(entry)
                if not old_inner: expected = pair
                assert tuple(rd(m, a, 2) for a in states) == expected
                for _ in range(80):
                    expected = tuple(decay(v, m[a]) for v, a in zip(expected, rates))
                    r.run(update)
                    assert (*[rd(m, a, 2) for a in states], rd(m, combined, 2)) == (*expected, max(expected))
                cases += 1
    return cases


def transient_setup(r, branch, count):
    m = reset(r)
    m[0xD87], m[0x896], m[0x898] = (9, 0, 0) if branch == 0 else (9, 16, 0) if branch == 1 else (0, 16, 255)
    m[0x900], m[0x8ED], m[0x8F4], m[0x8F5] = 60, 192, 80, 100
    for a, v in ((0x8E6, 200), (0x8CE, 24000), (0x8F2, 40000), (0x940, 1500), (0x95A, 1700), (0x95E, 200)):
        wr(m, a, 2, v)
    # Inclusive gates deliberately admit all chosen fixtures, while keeping the
    # supplied map cells and executing every actual lookup.
    for a in (0x34C5, 0x34C7, 0x3554, 0x3556): m[a], m[a+1] = 0, 255
    for a in (0x34C9, 0x34CA, 0x3558, 0x3559, 0x355A, 0x355B): m[a] = 128
    wr(m, 0x34CC, 2, 0)
    m[0x3551] = m[0x3552] = 255
    m[0xB21], m[0xCA8], m[0xDA4], m[0xDA5], m[0xDD9] = 1, 1, count, 2, 128
    m[0xE1] = 192
    wr(m, 0x44, 2, 65500)
    r.run((0xB8B6, 0xB8C2))
    assert m[0xA0F] == uniform_q8(m, 0x34FD, m[0x8F4])//256
    r.run((0x8F82, 0x8F9D))
    assert m[0xA05] == lookup(m, 0x3494, rd(m, 0x900, 2))
    r.run((0x8FA0, 0x8FD9))
    assert m[0xB18] == (1 if m[0x8EC] <= m[0xA05] else 0)
    return m


def pulse(m, curve):
    return extra_transient_ticks(lookup(m, 0x353A, rd(m, 0x8F2, 2)), m[0xA0F],
        uniform_q8(m, 0x351D, m[0x8F5])//256,
        uniform_q8(m, curve, m[0x8ED])//256, lookup(m, 0x34EE, rd(m, 0x8CE, 2)))


def transient(r):
    cases = 0
    for branch in range(3):
        for count in (0, 1, 2, 5, 255):
            for inhibited in (None, (0xD08, 1), (0x884, 1), (0x884, 2), (0x88C, 128),
                              (0x8B1, 16), (0x8B1, 128)):
                m = transient_setup(r, branch, count)
                first = pulse(m, (0x34D0, 0x34DA, 0x34E4)[branch])
                retained = pulse(m, (0x355D, 0x3567, 0x3571)[branch])
                if inhibited: m[inhibited[0]] |= inhibited[1]
                r.run((0x91B6, 0x95A6))
                assert rd(m, 0xA0A, 2) == first
                assert rd(m, 0xD02, 2) == retained
                p = clamp(clamp(retained+1500, rd(m, 0x19DA, 2), rd(m, 0x19DC, 2))+200)
                second = clamp((retained*m[0xCEC]*2+128)//256)
                s = clamp(clamp(second+1700, rd(m, 0x19DA, 2), rd(m, 0x19DC, 2))+200)
                assert (rd(m, 0xCF6, 2), rd(m, 0xCFC, 2)) == (p, s)
                assert bool(m[0xCF2]&1) == (count != 0 and inhibited is None)
                if inhibited is None:
                    immediate = min(25000, first)+200
                    assert rd(m, 0x926, 2) == immediate
                    assert rd(m, 0x5C, 2) == (65502+immediate)&65535
                    if branch == 2:
                        secondary = clamp((min(25000, first)*m[0xCEC]*2+128)//256+200)
                        assert rd(m, 0x5E, 2) == (65502+secondary)&65535
                    else: assert rd(m, 0x5E, 2) == 0
                else:
                    assert rd(m, 0x5C, 2) == rd(m, 0x5E, 2) == 0
                # Count actual output edges. The secondary path shares CF3/CF4;
                # one event on either channel advances the same episode.
                if count and inhibited is None:
                    m[0xE1] = 0
                    wr(m, 0x92A, 2, 1600); wr(m, 0x92C, 2, 1800)
                    for event in range(count+3):
                        secondary = branch == 2 and event%2
                        timer, handler, base = (0x5E, 0xF6C0, 1800) if secondary else (0x5C, 0xF607, 1600)
                        wr(m, 0xB74 if secondary else 0xB72, 2, base)
                        m[0xA18] = 0
                        old = rd(m, timer, 2)
                        active = event < count
                        duration = (s if secondary else p) if active else base
                        r.call(handler)
                        assert rd(m, timer, 2) == (old+duration)&65535, (event, count, secondary)
                        assert bool(m[0xCF2]&1) == (event+1 < count)
                        assert m[0xCF3] == min(event+1, count)
                        assert bool(m[0xCF2]&4) == (count <= event+1 < count+2)
                cases += 1
    return cases


def transient_rearm(r):
    cases = 0
    for branch in range(3):
        for change in (None, (0xB21, 0), (0xB21, 2), (0xB21, 255), (0x886, 64), (0x881, 16),
                       (0x34C5, 61), (0x34C6, 59), (0x34C7, 51), (0x34C8, 49),
                       (0x8ED, 127), (0x3551 if branch == 0 else 0x3552, 0)):
            m = transient_setup(r, branch, 2)
            if change: m[change[0]] = change[1]
            previous = m[0xB21]
            possible = pulse(m, (0x34D0, 0x34DA, 0x34E4)[branch])
            expected = possible if change is None else 0
            r.run((0x91B6, 0x95A6))
            assert rd(m, 0xA0A, 2) == expected, change
            assert bool(rd(m, 0x5C, 2)) == bool(expected), change
            if previous != 1: assert m[0xB21] == (previous-1)&255
            if change == (0x3551 if branch == 0 else 0x3552, 0):
                # Expiration resets the burst counter and accepts the next
                # pulse even if the within-window limit is zero.
                m[0xB21] = 1; m[0xB20] = 255; m[0xA16] = m[0xA18] = 0
                r.run((0x91B6, 0x95A6))
                assert rd(m, 0xA0A, 2) == possible
                assert m[0xB20] == m[0xB1C] == 0
            cases += 1
    return cases


def injection_phase(target, old, origin, step, enabled):
    difference = (target-origin)%24-(old-origin)%24
    if not enabled or abs(difference) <= step:
        return 10 if target == 11 else target
    if difference < 0:
        value = old-step
        if value < 0:
            value += 24
            if value == 23: value = 22
        return 10 if value == 11 else value
    value = old+step
    if value == 23: return 0
    if value > 23: value -= 24
    return 12 if value == 11 else value


def phase_dispatch(r):
    cases = 0
    for enabled in (False, True):
        for origin in (0, 6, 12, 18, 23):
            for old in (0, 10, 11, 12, 22, 23):
                for target in range(23):
                    for step in (0, 1, 4, 23):
                        m = reset(r)
                        m[0xD9B], m[0xD7E], m[0xD9C], m[0xA1A], m[0xA1B] = 128 if enabled else 0, origin, step, old, target
                        r.call(0xEC98)
                        expected = injection_phase(target, old, origin, step, enabled)
                        assert m[0xA1A] == m[0xA1E] == expected, (target, old, origin, step, enabled)
                        cases += 1
    # Phase-limiter output feeds the real dispatcher and normal timer writer.
    for variant in (0, 9):
        for special in (False, True):
            for target in (0, 1, 10, 12, 22):
                for inhibit in (None, (0x886, 4), (0x886, 2), (0x88C, 8), (0x88C, 16), (0x89A, 8), (0x89A, 4), (0x8B1, 128)):
                    m = reset(r)
                    m[0xD87], m[0xD9B], m[0xA1B], m[0xD9D] = variant, 0, target, 0
                    r.call(0xEC98); r.call(0xED11)
                    m[0xA1C], m[0xA1D] = m[0xA1E], m[0xA1F]
                    m[0x88B] = 128 if special else 0
                    m[0x923 if special else 0xC04] = target
                    m[0xE1] = 192
                    wr(m, 0x92A, 2, 1000); wr(m, 0x92C, 2, 1700); wr(m, 0x44, 2, 65000)
                    if inhibit: m[inhibit[0]] |= inhibit[1]
                    r.call(0xF4E0)
                    p = inhibit not in ((0x886, 4), (0x88C, 8), (0x89A, 8), (0x8B1, 128))
                    # An accepted primary dispatch clears 88C:30 before the
                    # secondary checks its gate; the 0x10 bit is not independent.
                    s = variant != 9 and inhibit not in ((0x886, 2), (0x89A, 4), (0x8B1, 128))
                    if inhibit == (0x88C, 16) and not p: s = False
                    assert rd(m, 0x5C, 2) == ((65002+1000)&65535 if p else 0), (variant, special, target, inhibit)
                    assert rd(m, 0x5E, 2) == ((65002+1700)&65535 if s else 0), (variant, special, target, inhibit)
                    cases += 1
    return cases


def injector_overlap(r):
    cases = 0
    for secondary in (False, True):
        timer, helper, request, duration, consumed, pending, override, saved, queued = (
            (0x5E, 0xC939, 0x928, 0xB74, 0xB78, 2, 32, 0xA2C, 32) if secondary else
            (0x5C, 0xC8C9, 0x926, 0xB72, 0xB76, 8, 128, 0xA2A, 128))
        for now in (0, 65000):
            for remaining in (0, 1, 100, 1000, 32767, 32768, 65535):
                for pin_high in (False, True):
                    for waiting in (False, True):
                        m = reset(r)
                        pin = 128 if secondary else 64
                        m[0xE1] = pin if pin_high else 0
                        m[0xA17], m[0xA18] = override, pending if waiting else 0
                        wr(m, 0x44, 2, now); wr(m, timer, 2, (now+remaining)&65535)
                        wr(m, request, 2, 500); wr(m, duration, 2, 700); wr(m, consumed, 2, 100)
                        guard = rd(m, 0x4F18, 2)
                        positive = lambda x: not (x&65535)&32768
                        fits = all(positive(x) for x in (remaining, remaining-500, remaining-500-guard))
                        if pin_high:
                            expected = 500 if not waiting or fits else 1200
                        else:
                            tail = (remaining-guard)&65535 if positive(remaining) and positive(remaining-guard) else 0
                            expected = (tail+500-100)&65535
                        r.call(helper)
                        assert rd(m, duration, 2) == expected
                        assert rd(m, consumed, 2) == 0
                        assert rd(m, timer, 2) == (now+2+expected)&65535
                        assert bool(m[0xA18]&queued) == bool(pin_high and waiting and fits)
                        if pin_high and waiting and fits: assert rd(m, saved, 2) == (now+remaining)&65535
                        cases += 1
        # Phase-aligned start, then the edge handler completes the pulse.
        for delay in (1, 30, 2000, 65535):
            m = reset(r); m[0xD87] = 0; m[0xD9B] = 0; m[0xA1B] = 12
            wr(m, 0xDAE, 2, delay)
            r.run((0x85A2, 0x85C0))
            assert rd(m, 0xA22, 2) == rd(m, 0xA24, 2) == delay
            m[0x88B], m[0x923], m[0xE1] = 128, 12, 192
            wr(m, 0xAF0, 2, 65000); wr(m, 0x92A, 2, 1000); wr(m, 0x92C, 2, 1700)
            r.call(0xF4E0)
            assert rd(m, timer, 2) == (65000+delay)&65535
            assert m[0xA18]&pending
            m[0xE1] = 0
            r.call(0xF6C0 if secondary else 0xF607)
            assert rd(m, timer, 2) == (65000+delay+(1700 if secondary else 1000))&65535
            assert not m[0xA18]&pending
            cases += 1
        # Special-mode dispatch while an earlier pulse is still pending/active.
        # Cover direct restart, deferred start and queued restart separately.
        for pin_high in (False, True):
            for remaining in (0, 7, 8, 100, 32768, 65535):
                for delay in (80, 130, 150):
                    for flags in (0, 1, 4):
                        m = reset(r)
                        m[0x88B] = 128; m[0xE1] = (128 if secondary else 64) if pin_high else 0
                        m[0xCF2], m[0xCF3], m[0xCF4], m[0xDA4], m[0xDA5] = flags, 1, 1, 2, 2
                        wr(m, 0x44, 2, 65000); wr(m, timer, 2, (65000+remaining)&65535)
                        wr(m, 0xAF0, 2, 64000); wr(m, 0xA24 if secondary else 0xA22, 2, delay)
                        wr(m, 0x4F18, 2, 40); wr(m, duration, 2, 700)
                        wr(m, 0x92A, 2, 1000); wr(m, 0x92C, 2, 1700)
                        wr(m, 0xCF6, 2, 2200); wr(m, 0xCFC, 2, 3300)
                        deferred = pin_high or remaining >= 32768 or remaining < 8
                        select = not deferred and remaining < delay
                        queue = select and remaining+40 < delay
                        value = (3300 if secondary else 2200) if flags&1 else (1700 if secondary else 1000)
                        r.call(0xC712 if secondary else 0xC55B)
                        expected_duration = value if select else 700
                        expected_timer = ((64000+delay) if deferred else (65000+remaining) if queue else (65002+expected_duration))&65535
                        assert rd(m, timer, 2) == expected_timer
                        assert rd(m, duration, 2) == expected_duration
                        assert bool(m[0xA18]&queued) == queue
                        assert rd(m, 0x92A, 2) == (value if select and flags&1 else 1000)
                        assert rd(m, 0x92C, 2) == 1700
                        assert m[0xCF2] == (4 if select and flags&1 else 0 if select and flags&4 else flags)
                        cases += 1
    return cases


def alternate_ignition(r):
    cases = 0
    # Ordered transitions retain the latch/counter between updates. Both
    # variants exercise neutral; neither is assigned to an unproven bike model.
    steps = [dict() for _ in range(4)] + [dict(throttle=255), dict(), dict(temp=128),
        dict(temp=112), dict(temp=80), dict(fault=4), dict(), dict(neutral=False),
        dict(period=250), dict(period=2), dict(delta=129), dict(), dict(), dict()]
    for variant in (0, 9):
        for gain in (128, 80):
            m = reset(r); m[0xD87] = variant
            m[0x4A31], m[0x4A32], m[0x4A30], m[0xD7C] = 100, 120, 3, 250
            m[0x4A2E], m[0x4A2F], m[0x4240] = 128, 2, 2
            m[0x4B03], m[0x4242], m[0xA83], m[0xD05] = 0, 200, 100, 64
            cold = False; count = 0
            for step in steps:
                temp, period, delta = step.get('temp', 80), step.get('period', 5), step.get('delta', 128)
                throttle, fault, neutral = step.get('throttle', 0), step.get('fault', 0), step.get('neutral', True)
                m[0x8F4], m[0x900], m[0x8ED], m[0x8EC], m[0x8AF] = temp, 20, delta, throttle, fault
                m[0xA2E], m[0x896], m[0xA86], m[0xA87] = period, 0 if neutral else 16, gain, 3
                r.run((0xB850, 0xB89E))
                expected_base = m[0x4A60+(temp-16)//16]
                assert m[0xA88] == expected_base
                threshold = uniform_q8(m, 0x4A33, temp)//256
                assert m[0xA89] == threshold
                cold = True if temp <= 100 else False if temp >= 120 else cold
                if 3 <= period < 250: count = min(255, count+1) if delta <= 128 else 0
                active = (3 <= period < 250 and delta <= 128 and count > 2 and threshold >= throttle
                          and not fault&12 and (variant != 9 or neutral) and cold)
                r.run((0x9664, 0x96F5))
                assert m[0xA8A] == count
                assert bool(m[0x885]&4) == cold and bool(m[0x885]&32) == active
                r.run((0x88F4, 0x8A89))
                recovered = min(128, gain+3) if gain < 128 else gain
                selected = (max(expected_base, 64) if active else 100)*recovered//128
                if m[0x880]&4: selected = 64
                assert m[0xA82] == selected
                # Feed that selected value through the real main-loop planner
                # caller, then charge/fire dispatch at simulated capture edges.
                pitch, dwell = 1600, 800
                for a, v in ((0xA36, 3*pitch), (0xA32, 3*pitch//4), (0xA30, pitch),
                             (0xDB4, 30), (0xA96, dwell), (0xDB0, 30), (0xA9A, 10)):
                    wr(m, a, 2, v)
                m[0xA8B] = 150
                event, advance, residual = fire_plan(selected, 4800, 1200, pitch, 150, 30, rd(m, 0x4F9E, 2))
                ce, cr = charge_plan(dwell, advance, 1200, pitch, 30)
                r.run((0x5416, 0x5435))
                assert (m[0x924], rd(m, 0xAA4, 2), m[0x925], rd(m, 0xAA2, 2)) == (event, residual, ce, cr)
                assert 1 <= ce <= 6
                m[0xA92] = m[0xA93] = m[0xE1] = 0
                wr(m, 0xAF0, 2, ((ce-6)*pitch)&65535); m[0xC04] = ce
                r.call(0xEE78)
                charge_time = (ce-6)*pitch+cr
                assert rd(m, 0x56, 2) == charge_time&65535
                assert m[0x49]&192 == 192
                m[0xE1] = 8; wr(m, 0xAF0, 2, ((event-6)*pitch)&65535); r.reg[1] = event
                r.call(0xEF6D)
                fire_time = (event-6)*pitch+residual
                blocked = bool(m[0x880]&4 or m[0x88D]&32)
                assert rd(m, 0x56, 2) == (charge_time if blocked else fire_time)&65535
                assert m[0x49]&192 == (192 if blocked else 128)
                assert fire_time-charge_time == dwell
                cases += 1
    return cases


def build():
    codes = {f:load_code(f) for f in ('early', 'late')}; results = []
    for e in json.loads((ROOT/'analysis/firmware/catalog.json').read_text())['images']:
        raw = (ROOT/e['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == e['sha256']
        family = e['code_family']
        r = Sequence(b'\xff'*e['base_address']+raw, codes[family])
        checks = dict(post_start_lifecycle=post_start(r, family))
        if family == 'early':
            checks.update(transient_to_output=transient(r), transient_rearm=transient_rearm(r), phase_and_dispatch=phase_dispatch(r),
                          injector_overlap_and_delayed_edges=injector_overlap(r),
                          alternate_ignition_to_coil=alternate_ignition(r))
        results.append(dict(id=e['id'], firmware_sha256=e['sha256'], checks=checks,
            instruction_addresses=[f'0x{a:04X}' for a in sorted(r.executed)]))
        print(e['id'], checks, flush=True)
    return dict(result='passed', cases=sum(sum(e['checks'].values()) for e in results), images=results,
        test_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        dependencies={n:hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest() for n in
            ['map_models.py','spark_models.py','test_input_coordinates.py','test_pressure_sources.py','test_speed_sources.py','test_firmware_lookups.py','test_full_lift.py']},
        limits=['Post-start: both families. Transient, phase and alternate ignition: early family only', 'No autonomous peripherals; timer pin levels are fixture inputs',
                'Sequenced branch fixtures are not exhaustive concurrent execution', 'No physical sensor, clock or crank reference verification'])


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--check', action='store_true'); args = ap.parse_args()
    result = build()
    if args.check: assert json.loads(REPORT.read_text()) == result, 'Operating sequence report is stale'
    else: REPORT.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    print('Operating sequences:', result['cases'], 'passed')
