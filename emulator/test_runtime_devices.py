"""Independent timer, clock/watchdog and SPI register checks."""
import re
from test_peripherals import Checks, word
from runner import execute, RUNS


def test_timer_spi(executable,wsl):
    c=Checks()
    def reset():
        c.commands.append('reset\nCC=0xd0\nSP=0xff0\nfill rom 0x1200 0x2fff 0xa7\n')
    reset()
    c.code([0x86,0xff,0x5a,0x33,0x5a,0x32,0x96,0x32],4)
    c.check('port K implements only pin seven','(A==128)&&(rom[0x33]==128)')
    for prescale in range(8):
        reset()
        c.commands.append(f'set memory rom 0x4d {prescale}\n')
        c.code([0x86,0x80,0x5a,0x46],2)
        c.wait(128)
        c.check(f'timer prescaler /{1<<prescale}',word(0x44,130//(1<<prescale)))
    reset()
    c.commands.append('set memory rom 0x44 0x12 0x34\n')
    c.code([0xcc,0x56,0x78,0x5c,0x44],2)
    c.check('TCNT read-only in normal mode',word(0x44,0x1234))
    for n in range(8):
        reset()
        c.commands.append(f'set memory rom 0x40 {1<<n}\nset memory rom {0x48 if n>=4 else 0x49} {3<<(2*(n%4))}\nset memory rom {0x50+2*n} 0 4\nset memory rom 0x46 0x80\n')
        c.wait(3)
        c.check(f'OC{n} not early',f'(rom[0x4e]&{1<<n})==0')
        c.wait(1)
        c.code([0x96,0xe0],1)
        c.check(f'OC{n} match flag and output',f'((rom[0x4e]&{1<<n})!=0)&&((A&{1<<n})!=0)')
        c.code([0x86,1<<n,0x5a,0x4e],2)
        c.check(f'OC{n} W1C',f'(rom[0x4e]&{1<<n})==0')
    reset()
    c.commands.append('set memory rom 0x40 8\nset memory rom 0x49 0xc0\n')
    c.code([0x86,8,0x5a,0x41,0x96,0xe0],3)
    c.check('force compare updates pin without IRQ','((A&8)!=0)&&(rom[0x4e]==0)&&(rom[0x41]==0)')
    # Channel seven override and compare reset; overflow is suppressed at FFFF.
    reset()
    c.commands.append('set memory rom 0x40 0x88\nset memory rom 0x42 8\nset memory rom 0x43 8\nset memory rom 0x5e 0 4\nset memory rom 0x4d 8\nset memory rom 0x46 0x80\n')
    c.wait(4)
    c.check('TCRE resets on channel seven',word(0x44,0)+'&&((rom[0x4e]&128)!=0)')
    c.code([0x96,0xe0],1)
    c.check('OC7 overrides masked output','(A&8)!=0')
    c.commands.append('set memory rom 0x5e 0xff 0xff\nset memory rom 0x44 0xff 0xfe\n')
    c.wait(1)
    c.check('TCRE at FFFF prevents overflow',word(0x44,0)+'&&(rom[0x4f]==0)')
    reset()
    c.commands.append('set memory rom 0x44 0xff 0xfe\nset memory rom 0x46 0x80\n')
    c.wait(2)
    c.check('timer wrap sets TOF',word(0x44,0)+'&&(rom[0x4f]==128)')
    c.code([0x86,0x90,0x5a,0x46,0xdc,0x44],3)
    c.check('TFFCA counter read clears TOF','rom[0x4f]==0')
    for edge,old,new,accepted in [(1,0,2,True),(1,2,0,False),(2,2,0,True),(2,0,2,False),(3,0,2,True),(3,2,0,True)]:
        reset()
        c.commands.append(f'set memory xtboot_0_cfg 12 {old}\n')
        c.wait(1)
        c.commands.append(f'set memory rom 0x44 0x12 0x34\nset memory rom 0x4b {edge<<2}\nset memory rom 0x46 0x80\nset memory xtboot_0_cfg 12 {new}\n')
        c.wait(1)
        expr=word(0x52,0x1234)+'&&((rom[0x4e]&2)!=0)' if accepted else '(rom[0x4e]&2)==0'
        c.check(f'IC edge mode {edge} {old}->{new}',expr)
    reset()
    c.commands.append('set memory rom 0x4e 2\nset memory rom 0x46 0x10\nset memory rom 0x52 0x12 0x34\n')
    c.code([0xdc,0x52],1)
    c.check('TFFCA capture read clears matching flag','(D==0x1234)&&(rom[0x4e]==0)')
    # SPI full duplex byte timing, data latch, transmit qualification and queue.
    for baud,period in [(0,16),(1,32),(3,128),(0x12,128)]:
        reset()
        c.commands.append(f'set memory rom 0xd8 0x50\nset memory rom 0xda {baud}\nset memory xtboot_0_cfg 17 0xa6\n')
        c.code([0x86,0x55,0x5a,0xdd],2)
        c.wait(period+4)
        c.check(f'SPI {baud:02x} ignores unqualified write','(rom[0xdb]==32)&&(rom[0xdd]==0)')
        c.code([0x96,0xdb,0x86,0x55,0x5a,0xdd],3)
        c.wait(period-3)
        c.check(f'SPI {baud:02x} transfer not immediate','(rom[0xdb]&128)==0')
        c.wait(1)
        c.check(f'SPI {baud:02x} transfer completes','((rom[0xdb]&128)!=0)&&(rom[0xdd]==0xa6)')
        c.code([0x96,0xdd],1)
        c.check(f'SPI {baud:02x} data without status retains SPIF','(rom[0xdb]&128)!=0')
        c.code([0x96,0xdb,0x96,0xdd],2)
        c.check(f'SPI {baud:02x} status/data acknowledges','(A==0xa6)&&((rom[0xdb]&128)==0)')
    reset()
    c.commands.append('set memory rom 0xd8 0x50\nset memory rom 0xda 3\nset memory xtboot_0_cfg 18 1\n')
    c.code([0x96,0xdb,0x86,0x55,0x5a,0xdd,0x96,0xdb,0x86,0xaa,0x5a,0xdd],6)
    c.check('SPI queued byte occupies transmit buffer','(rom[0xdb]&32)==0')
    c.wait(300)
    c.check('SPI unread overrun preserves first byte','(rom[0xdd]==0x55)&&(rom[0xdb]==0xa0)')
    # Interrupts from actual timer and SPI events.
    for vector,setup in [(0xffee,'set memory rom 0x40 1\nset memory rom 0x50 0 10\nset memory rom 0x4c 1\nset memory rom 0x46 128\n'),(0xffde,'set memory rom 0x44 255 250\nset memory rom 0x4d 128\nset memory rom 0x46 128\n')]:
        reset()
        c.commands.append(setup+f'set memory rom {vector} 0x11 0\nCC=0\nbreak 0x1100\n')
        c.wait(100)
        c.check(f'timer IRQ {vector:04x}','(PC==0x1100)&&(SP==0xfe7)')
        c.commands.append('delete\n')
    reset()
    c.commands.append('set memory rom 0xd8 0xd0\nset memory rom 0xffd8 0x11 0\n')
    c.code([0x96,0xdb,0x86,0x55,0x5a,0xdd],3)
    c.commands.append('CC=0\nbreak 0x1100\n')
    c.wait(40)
    c.check('SPI completion IRQ','(PC==0x1100)&&(SP==0xfe7)')
    c.commands.append('delete\n')
    # RTI derives from the oscillator, not the bus rate.
    reset()
    c.commands.append('set memory rom 0x34 7\nset memory rom 0x35 1\nset memory rom 0x39 128\n')
    c.code([0x86,0x10,0x5a,0x3b],2)
    # The three setup cycles leave the bus/oscillator divider at phase 3/4.
    c.wait(4092)
    c.check('RTI waits for oscillator period','(rom[0x37]&128)==0')
    c.wait(1)
    c.check('RTI period completed','(rom[0x37]&128)!=0')
    c.commands.append('set memory rom 0x38 128\nset memory rom 0xfff0 0x11 0\nCC=0\n')
    c.code([0xa7],1)
    c.check('RTI interrupt delivered','PC==0x1100')
    return c.run(executable,wsl,'timer-spi.log')


def test_watchdog(executable,wsl):
    # Separate process per reset-stop expectation, with a tight firmware loop.
    results=[]
    for service in (False,True):
        code='0x86 0x55 0x5a 0x3f 0x86 0xaa 0x5a 0x3f 0x20 0xf6' if service else '0xa7 0x20 0xfd'
        script=f'''reset
set memory rom 0x1000 0x86 1 0x5a 0x3c
pc 0x1000
step 2
set memory rom 0x1100 {code}
pc 0x1100
step 20000
info hardware xtboot
quit
'''
        out=execute(executable,script,wsl)
        (RUNS/f'watchdog-{service}.log').write_text(out,encoding='utf-8')
        if service:
            assert 'FAULT=0' in out and 'unmodelled' not in out
            assert int(re.search(r'COP_SERVICES=(\d+)',out)[1])>100
        else:
            assert 'COP timeout reset request' in out and 'FAULT=1' in out
        results.append('serviced watchdog stays running' if service else 'unserviced watchdog requests reset')
    return results


def test_runtime(executable,wsl):
    from runtime import runtime
    images=['xt660-2004-2006-companion','xt660-5vk-1x-2008','xt660-2c1-10','xt660-2c1-10-immo-off','xt660-5vk-11']
    reports=[]
    for image in images:
        report=runtime(executable,image,wsl,loops=1000,verify_flash=True)
        assert report['completed'], report
        counts=report['counts']
        assert counts['rti_events']>=10 and counts['irq_count']>=10, report
        assert counts['cop_services']>10 and counts['spi_bytes']>0, report
        assert counts['adc_sequences']>10 and counts['captures']==0, report
        # Keep machine-local trace paths out of the portable validation report.
        report.pop('trace')
        reports.append(report)
    return reports


def test_runtime_guards(executable,wsl):
    rows=[]
    for name,code,reason in [
        ('SCI transmit',[0x86,0x55,0x5a,0xcf],'SCI transmit'),
        ('SCI transmit interrupt',[0x86,0x80,0x5a,0xcb],'SCI interrupt/break/wakeup'),
        ('SPI slave',[0x86,0x40,0x5a,0xd8],'SPI slave'),
        ('COP invalid service',[0x86,0x12,0x5a,0x3f],'COP reset request'),
        ('COP early window service',[0x86,0x81,0x5a,0x3c,0x86,0x55,0x5a,0x3f],'COP reset request'),
        ('ATD external trigger',[0x86,0x84,0x5a,0x82],'external ATD trigger')]:
        command='reset\nset memory rom 0x1000 '+' '.join(hex(v) for v in code)+'\npc 0x1000\nstep 20\ninfo hardware xtboot\nquit\n'
        output=execute(executable,command,wsl)
        assert reason in output and 'FAULT=1' in output,name
        rows.append(name)
    return rows
