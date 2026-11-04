"""Logger display profile: accept every normal reply once, never UI snapshots."""
from meter import MeterPeer


def reply(pulses):
    return [0, pulses, 0, 57, (pulses + 57) & 255]


def check():
    meter = MeterPeer()
    for _ in range(7):
        meter.accept(reply(5))
    assert meter.state()['speed_mph'] is None
    before = meter.state()
    for _ in range(30):
        assert meter.state() == before
    invalid = reply(5)
    invalid[4] ^= 1
    try:
        meter.accept(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid checksum accepted')
    assert meter.state() == before
    meter.accept(reply(5))
    assert meter.state()['speed_kmh'] == 40
    assert abs(meter.state()['speed_mph'] - 24.85484768949336) < 1e-10
    for _ in range(7):
        meter.accept(reply(0))
        assert meter.state()['speed_kmh'] == 40
    meter.accept(reply(0))
    assert meter.state()['speed_mph'] == 0
    for _ in range(8):
        meter.accept(reply(255))
    assert meter.state()['speed_kmh'] == 2040
    meter.mode = 'diagnostic'
    meter.accept(reply(255))
    assert meter.state()['speed_mph'] is None
    meter.mode = 'normal'
    for _ in range(8):
        meter.accept(reply(5))
    assert meter.state()['speed_kmh'] == 40
    assert MeterPeer().state()['speed_mph'] is None
    print('Meter display: eight-reply sums, conversion, zero, overflow, rejected frames, snapshots and resets passed.')


if __name__ == '__main__':
    check()
