"""Immediate starter operation through external pins; no firmware flag writes."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from cockpit import Cockpit
from dashboard import available_images
from runner import registered_image


def check(executable, wsl):
    reports = []
    for row in available_images():
        b = Cockpit(executable, wsl)
        try:
            b.select(row['id'])
            started = time.perf_counter()
            b.power(True)
            key_seconds = time.perf_counter() - started
            key_cycles = b.engine.cycles
            key_reply = b.meter.frame[:]
            assert b.engine.authentication_required == (b.auth == 'Key accepted')
            assert b.auth in ('Key accepted', 'Disabled in BIN')
            # Start immediately after key-on. The host must not execute a
            # hidden settling interval before closing the starter contact.
            started = time.perf_counter()
            b.start()
            start_seconds = time.perf_counter() - started
            assert b.engine.cycles == key_cycles
            assert b.starting and not b.rotating
            frame_count = b.meter.frames
            for ticks in range(1, 17):
                b.tick()
                if b.rotating:
                    break
            assert b.rotating and not b.starting, (row['id'], b.state())
            assert b.engine.snapshot()['synchronized']
            assert b.meter.frames > frame_count
            assert b.meter.state()['fault'] == 0
            for channel in (3, 6):
                assert sum(e['kind'] == 'output' and e['channel'] == channel and
                           e['cycle'] > key_cycles for e in b.engine.trace) >= 4
            # Exercise both ends of the control and let the real ADC/filter/
            # serial paths respond. The percent is fixture travel, not angle.
            for throttle in (0, 100, 0):
                b.control('throttle', throttle)
                assert b.engine.adc[0] == 120 + throttle * 7
                for _ in range(25):
                    b.tick()
                    assert b.rotating and b.meter.state()['fault'] == 0, b.state()
            flash = b.engine.verify_flash()
            assert flash == 59392
            reports.append(dict(image=row['id'], source_sha256=registered_image(row['id'])[0]['sha256'],
                authentication=b.auth, key_on_host_seconds=round(key_seconds, 4),
                starter_command_host_seconds=round(start_seconds, 4),
                starter_command_added_bus_cycles=0, key_on_bus_cycles=key_cycles,
                key_on_reply=key_reply, ticks_until_firing=ticks,
                synchronized=True, sustained_control_sequence=[0, 100, 0],
                unchanged_flash_bytes=flash))
            print('Immediate start PASS ' + row['id'], flush=True)
        finally:
            b.power(False)
    # Failed authentication must still stop the starter; no startup speed-up
    # is permitted to bypass the actual SCI challenge/response result.
    for image in ('xt660-2004-2006-companion', 'xt660-2c1-10'):
        b = Cockpit(executable, wsl)
        try:
            b.select(image)
            b.power(True, wrong_key=True)
            assert b.auth == 'Key rejected'
            try:
                b.start()
            except ValueError as error:
                assert str(error) == 'The ECU rejected this key'
            else:
                raise AssertionError('Starter accepted rejected key')
            assert not b.starting and not b.rotating
            assert b.engine.verify_flash() == 59392
            reports.append(dict(image=image, rejected_key_prevents_start=True))
        finally:
            b.power(False)
    return reports


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--ucsim', required=True)
    parser.add_argument('--wsl', action='store_true')
    args = parser.parse_args()
    report = dict(scope='External starter initial state, immediate start, throttle fixtures, authentication; not physical timing validation',
                  checks=check(args.ucsim, args.wsl))
    here = Path(__file__).resolve().parent
    report['source_hashes'] = {p.relative_to(here).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [here/'cockpit.py', here/'engine.py', here/'runner.py', here/'meter.py',
                  here/'native/xt660_boot.cc', Path(__file__)]}
    (here/'startup-validation.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
