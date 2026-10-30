"""Replay speed-history, source selection and spark planning for all registered BINs.

Independent integer expectations versus the existing CPU12 p-code interpreter.
Every executed instruction is checked against the supplied BIN's bytes. No ECU
firmware is edited; peripheral timings and the mechanical TDC reference are not
inputs to these tests. --check compares the stored deterministic evidence report.
"""
import argparse
import hashlib
import json
import random
from collections import deque
from pathlib import Path

from spark_models import fire_plan
from test_firmware_lookups import load_code, reference, rd, wr

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'analysis/firmware/speed_source_validation.json'
LAYOUTS = {
    'early': dict(history=(0xEB0B, 0xEBC6), count=0xA52, index=0xA53,
                  ring=0xA54, total=0xA4F, published=0xA4B, capture=0xC07,
                  speed=(0x73A5, 0x74B7), periods=0xA38, period=0xA44,
                  stale=0x921, short_speed=0x8F8, filtered=0x8FE,
                  history_period=0xA80, history_speed=0x906,
                  selector=0x18D7, fuel_axis=0x900, spark_axis=0x902,
                  divisor=0x4E34, payload=0xAE2,
                  planner=(0x54F0, 0x55B5), pitch=0xA30, three=0xA36,
                  quarter=0xA32, correction=0xA8B, minimum=0xDB4,
                  offset=0x4F9E, event=0xDE3, advance=0xDE5, residual=0xDE7),
    'late': dict(history=(0xDFFE, 0xE0B9), count=0xA5C, index=0xA5D,
                 ring=0xA5E, total=0xA59, published=0xA55, capture=0xC29,
                 speed=(0x6B36, 0x6C48), periods=0xA42, period=0xA4E,
                 stale=0x941, short_speed=0x918, filtered=0x91E,
                 history_period=0xA8A, history_speed=0x926,
                 selector=0x18B2, fuel_axis=0x920, spark_axis=0x922,
                 divisor=0x45D2, payload=0xB05,
                 planner=(0x4D49, 0x4E0E), pitch=0xA3A, three=0xA40,
                 quarter=0xA3C, correction=0xA93, minimum=0xE1C,
                 offset=0x474E, event=0xE67, advance=0xE69, residual=0xE6B),
}


class Replay:
    def __init__(self, image, code):
        self.image, self.code = image, code
        self.ram = bytearray(0x1800) + image[0x1800:]
        self.reg = bytearray(64)
        self.executed = set()

    def run(self, bounds):
        pc, stop = bounds
        wr(self.reg, 42, 2, 0x1700)
        for _ in range(1200):
            if pc == stop:
                return
            row = self.code[pc]
            raw = bytes.fromhex(row['bytes'])
            assert self.image[pc:pc + len(raw)] == raw, hex(pc)
            self.executed.add(pc)
            result, pc = reference(row, self.ram, self.reg)
            assert result == 0
        raise AssertionError(('instruction bound', hex(pc)))


def reciprocal(period):
    # Fixtures keep the input in the independently established no-overflow range.
    assert 1200 <= period <= 65535
    return min(0xFE00, 8 * (37500 * 256 // period))


def history_cases(replay, layout, samples):
    """Compare each history update, including first-event skip and warmup."""
    m = replay.ram
    for key, size in [('count', 1), ('index', 1), ('total', 3)]:
        wr(m, layout[key], size, 0)
    wr(m, layout['published'], 3, 0xFFFFFF)
    for n in range(22):
        wr(m, layout['ring'] + 2 * n, 2, 0)
    history = deque(maxlen=22)
    count = index = 0
    published = 0xFFFFFF
    for sample in samples:
        wr(m, layout['capture'], 3, sample)
        count = min(255, count + 1)
        if count > 1:
            history.append(min(sample, 65535))
            total = sum(history)
            published = total if len(history) == 22 else (total // len(history)) * 22
            index = (index + 1) % 22
        replay.run(layout['history'])
        assert m[layout['count']] == count
        assert m[layout['index']] == index
        assert rd(m, layout['total'], 3) == sum(history)
        assert rd(m, layout['published'], 3) == published
    return len(samples)


def speed_case(replay, layout, period, history_sum, selector, stale=0, filtered=12344):
    m = replay.ram
    # Six distinct-sized components whose exact sum is the desired period.
    for n in range(6):
        wr(m, layout['periods'] + 2 * n, 2, period // 6 + (n < period % 6))
    wr(m, layout['published'], 3, history_sum)
    wr(m, layout['filtered'], 2, filtered)
    m[layout['selector']] = selector
    m[layout['stale']] = stale
    replay.run(layout['speed'])
    p = 65535 if stale >= 64 else min(period, 65535)
    short = 480 if stale >= 64 else reciprocal(p)
    history_period = min(65535, history_sum // 4)
    smooth = reciprocal(history_period)
    assert rd(m, layout['period'], 2) == p
    assert rd(m, layout['short_speed'], 2) == short
    assert rd(m, layout['history_period'], 2) == history_period
    assert rd(m, layout['history_speed'], 2) == smooth
    assert rd(m, layout['fuel_axis'], 2) == (smooth if selector else short)
    assert rd(m, layout['spark_axis'], 2) == (smooth if selector else filtered)
    payload_source = smooth if selector else short
    divisor = max(1, rd(m, layout['divisor'], 2))
    assert m[layout['payload']] == min(255, payload_source // divisor)


def build():
    catalog = json.loads((ROOT / 'analysis/firmware/catalog.json').read_text())
    codes = {family: load_code(family) for family in LAYOUTS}
    results = []
    for entry in catalog['images']:
        raw = (ROOT / entry['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry['sha256']
        image = b'\xFF' * entry['base_address'] + raw
        family = entry['code_family']
        layout = LAYOUTS[family]
        replay = Replay(image, codes[family])
        stock_selector = image[layout['selector']]
        assert stock_selector == 1
        history_count = steady_count = speed_count = spark_count = 0
        # Ten ordinary captures plus one double interval. Two patterns occupy
        # exactly 22 captured intervals and 24 normalized pitches.
        steady_examples = []
        for pitch in (256, 513, 800, 1600, 2400, 5000, 10000):
            samples = [pitch * (2 if n % 11 == 10 else 1) for n in range(67)]
            history_count += history_cases(replay, layout, samples)
            assert rd(replay.ram, layout['published'], 3) == 24 * pitch
            speed_case(replay, layout, 6 * pitch, 24 * pitch, stock_selector)
            assert rd(replay.ram, layout['history_period'], 2) == 6 * pitch
            assert rd(replay.ram, layout['short_speed'], 2) == rd(replay.ram, layout['history_speed'], 2)
            steady_examples.append(dict(pitch_ticks=pitch, history_ticks=24 * pitch,
                                        reciprocal_period_ticks=6 * pitch,
                                        speed_code=reciprocal(6 * pitch)))
            steady_count += 1
        rng = random.Random(66022)
        history_count += history_cases(replay, layout,
            [0, 1, 65535, 65536, 0xFFFFFF] + [rng.randrange(0x1000000) for _ in range(300)])
        for period in (1200, 1536, 2054, 2055, 3078, 9600, 30000, 60000, 65535, 100000):
            for history_sum in (4800, 8216, 8217, 8220, 38400, 240000, 262143, 262144, 0xFFFFFF):
                for selector in (0, 1, 128):
                    speed_case(replay, layout, period, history_sum, selector)
                    speed_count += 1
        # Stale short-period path and the stock history selector are separate.
        for stale in (64, 255):
            for selector in (0, 1):
                speed_case(replay, layout, 9600, 38400, selector, stale)
                speed_count += 1
        # A changing period history must not be replaced with the newest sample.
        for n in range(60):
            pitch = 800 if n < 30 else 1600
            sample = pitch * (2 if n % 11 == 10 else 1)
            if n == 0:
                history = []
            history.append(sample)
            history_count += history_cases(replay, layout, history)
            if n >= 23:
                speed_case(replay, layout, 6 * pitch,
                           rd(replay.ram, layout['published'], 3), stock_selector)
                speed_count += 1
        m = replay.ram
        offset = rd(image, layout['offset'], 2)
        assert offset == 150
        # All final timing codes, with independently varied period/correction.
        for timing_code in range(256):
            pitch = (513, 1600, 5000)[timing_code % 3]
            correction = (0, 150, 255)[(timing_code // 3) % 3]
            minimum = (1, 10, 100)[(timing_code // 9) % 3]
            three = pitch * 3
            for key, value in [('pitch', pitch), ('three', three),
                               ('quarter', three // 4), ('minimum', minimum)]:
                wr(m, layout[key], 2, value)
            m[layout['correction']] = correction
            replay.reg[0] = timing_code
            replay.run(layout['planner'])
            expected = fire_plan(timing_code, three, three // 4, pitch, correction, minimum, offset)
            actual = (m[layout['event']], rd(m, layout['advance'], 2), rd(m, layout['residual'], 2))
            assert actual == expected, (entry['id'], timing_code, actual, expected)
            spark_count += 1
        results.append(dict(id=entry['id'], firmware_sha256=entry['sha256'], family=family,
                            stock_source_selector=stock_selector, telemetry_divisor=rd(image, layout['divisor'], 2),
                            spark_offset_ticks=offset,
                            checks=dict(history_updates=history_count, steady_source_equivalence=steady_count,
                                        source_and_payload_cases=speed_count, spark_planner_cases=spark_count),
                            executed_instructions=len(replay.executed), steady_examples=steady_examples))
    return dict(result='passed', images=results,
                cases=sum(sum(r['checks'].values()) for r in results),
                test_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                interpreter_sha256=hashlib.sha256((ROOT / 'scripts/test_full_lift.py').read_bytes()).hexdigest(),
                spark_model_sha256=hashlib.sha256((ROOT / 'scripts/spark_models.py').read_bytes()).hexdigest(),
                scope='Instruction-byte-checked p-code execution of the history update, reciprocal/source selection, '
                      'telemetry and ordinary spark planner in all nine supplied BINs. Synthetic inputs; '
                      'not whole-ECU execution, an oscillator measurement or a physical crank/TDC reference.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    report = build()
    if args.check:
        assert json.loads(REPORT.read_text()) == report, 'stale speed-source report'
    else:
        REPORT.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f"Speed sources and spark planning: {report['cases']} checks, {len(report['images'])} BINs passed.")
