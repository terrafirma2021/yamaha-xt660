"""External fixture checks: real capture edges and ADC samples, no ECU patches."""
import argparse
import json
from test_peripherals import Checks, word
from runner import execute
from crank import events


def check(executable,wsl):
    c=Checks()
    c.setup()
    c.check('PWM reset latches while disabled',
            '&&'.join(f'rom[{a}]=={0 if a<0xb4 else 255}' for a in range(0xac,0xc4)))
    c.code([0x86,0x35,0x5a,0xbc,0x5a,0xb4,0x5a,0xac],4)
    c.wait(200)
    c.check('disabled PWM counter clears and duty/period retain writes',
            '(rom[0xac]==0)&&(rom[0xb4]==0x35)&&(rom[0xbc]==0x35)')
    # Fuel relay feedback must follow the output latch, not overwrite ADC RAM.
    for enabled,relay,expected in [(0,0,700),(1,0,0),(1,4,700)]:
        c.setup(ctl5=0x84)
        c.commands.append(f'adc4=700\nset memory rom 0x2 4\nset memory rom 0 {relay}\n'
                          f'set memory xtboot_0_cfg 40 {enabled}\n')
        c.wait(40)
        c.check(f'relay feedback enabled={enabled} relay={relay}',word(0x90,expected))
    # A disconnected MAP stays disconnected, even with the external waveform.
    c.setup(ctl5=0x81)
    c.commands.append('adc1=0\nset memory xtboot_0_cfg 39 255\nset memory xtboot_0_cfg 24 1\n')
    c.wait(40)
    c.check('pressure waveform never underflows a disconnected input',word(0x90,0))
    # Ignition driver pulses are observed by TC5's edge detector.
    for feedback in (0,1):
        c.commands.append('reset\nCC=0xd0\nfill rom 0x1200 0x2fff 0xa7\n'
                          'set memory rom 0x40 8\nset memory rom 0x49 0xc0\n'
                          'set memory rom 0x4a 8\nset memory rom 0x46 128\n'
                          f'set memory xtboot_0_cfg 41 {feedback}\nset memory xtboot_0_cfg 25 1\n')
        c.code([0x86,8,0x5a,0x41],2)  # set PT3 using force compare
        c.commands.append('set memory rom 0x49 0x80\n')
        c.code([0x86,8,0x5a,0x41],2)  # release PT3
        c.wait(200)
        c.check(f'coil feedback capture enabled={feedback}',f'(rom[0x4e]&32)=={32 if feedback else 0}')
    count=c.run(executable,wsl,'bike-inputs.log')
    # Road pulses run independently from crank and stop without a trailing fall.
    out=execute(executable,'reset\nCC=0xd0\nfill rom 0x1000 0x3fff 0xa7\npc 0x1000\n'
                'set memory rom 0x4b 32\nset memory rom 0x46 128\n'
                'set memory xtboot_0_cfg 25 1\nset memory xtboot_0_cfg 36 1000\n'
                'step 3500\nset memory xtboot_0_cfg 36 0\nstep 1000\nquit\n',wsl)
    falls=[e['cycle'] for e in events(out) if e['kind']=='input' and e['channel']==2 and e['value']==0]
    captures=[e['cycle'] for e in events(out) if e['kind']=='capture' and e['channel']==2]
    assert falls==[1000,2000,3000],falls
    assert captures==falls,captures
    return dict(register_checks=count,road_input_and_capture_edges=falls)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ucsim',required=True);p.add_argument('--wsl',action='store_true');a=p.parse_args()
    print(json.dumps(check(a.ucsim,a.wsl),indent=2))
