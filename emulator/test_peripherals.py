"""ATD/GPIO/interrupt fixtures plus execution of unchanged firmware ADC routines."""
import re
from runner import RUNS, execute, prepare, registered_image


class Checks:
    def __init__(self):
        self.commands = []
        self.names = []

    def code(self, data, steps=None):
        self.commands.append('set memory rom 0x1000 ' + ' '.join(hex(v) for v in data) + '\npc 0x1000\n')
        if steps is not None:
            self.commands.append(f'step {steps}\n')

    def setup(self, ctl2=0x80, ctl3=8, ctl4=0, ctl5=0):
        self.commands.append('reset\nfill rom 0x1200 0x1fff 0xa7\nCC=0xd0\nSP=0xff0\n')
        data = []
        for reg, value in [(0x82,ctl2),(0x83,ctl3),(0x84,ctl4),(0x85,ctl5)]:
            data += [0x86,value,0x5a,reg]
        self.code(data,8)

    def wait(self, cycles):
        self.commands.append(f'pc 0x1200\nstep {cycles}\n')

    def check(self, name, expression):
        index = len(self.names)
        self.names.append(name)
        self.commands.append(f'expression /X (0x66000000+{2*index}+({expression}))\n')

    def run(self, executable, wsl, filename):
        output = execute(executable, ''.join(self.commands)+'quit\n', wsl, timeout=60)
        (RUNS/filename).write_text(output)
        values = [int(v,16) for v in re.findall(r'(?m)^0x(66[0-9a-fA-F]{6})\s*$', output)]
        assert len(values)==len(self.names), (filename,len(values),len(self.names))
        failed = [name for i,(name,value) in enumerate(zip(self.names,values)) if value!=0x66000001+2*i]
        assert not failed, (filename,failed)
        assert 'FAULT=1' not in output and 'unmodelled' not in output and 'Parser error' not in output, filename
        return len(values)


def word(address, value):
    return f'(rom[{address}]=={value>>8})&&(rom[{address+1}]=={value&255})'


def test_peripherals(executable,wsl):
    c=Checks()
    # The expected results come from the datasheet representation, not the model.
    for raw in (0,1,3,511,512,1022,1023):
        for eight in (False,True):
            for mode in (0,0x40,0x80,0xc0):
                c.setup(ctl4=0x80 if eight else 0,ctl5=mode)
                c.commands.append(f'adc0={raw}\n')
                c.wait(40)
                value=raw//4 if eight else raw
                if not mode&0x80:
                    if mode&0x40: value ^= 128 if eight else 512
                    value *= 256 if eight else 64
                c.check(f'ADC format raw={raw} eight={eight} mode={mode:02x}',word(0x90,value)+'&&(rom[0x8b]==1)&&((rom[0x86]&0x80)!=0)')
    c.setup()
    c.wait(25) # STAA consumed 2 bus cycles; full conversion requires 28.
    c.check('ADC is not immediately complete','(rom[0x8b]==0)&&((rom[0x86]&0x80)==0)')
    c.wait(1)
    c.check('ADC minimum conversion timing','(rom[0x8b]==1)&&((rom[0x86]&0x80)!=0)')
    # Firmware's prescaler=3, second sample phase=16: 224 bus cycles/result.
    c.setup(ctl3=0x40,ctl4=0x63,ctl5=0x16)
    values=[3,50,123,256,511,512,777,1023]
    for i,v in enumerate(values): c.commands.append(f'adc{i}={v}\n')
    c.wait(221)
    c.check('firmware ADC first result still pending','rom[0x8b]==0')
    c.wait(1)
    c.check('MULT starts at channel six',word(0x90,777*64)+'&&(rom[0x8b]==1)')
    c.wait(7*224)
    c.check('MULT wraps through channel zero','&&'.join(word(0x90+i*2,values[(i+6)%8]*64) for i in range(8))+'&&(rom[0x8b]==255)')
    # Read-before-status must not acknowledge CCF. Debugger reads never do.
    c.code([0x86,0,0x5a,0x90,0x5a,0x8b],3)
    c.check('ADC results and CCF are read-only',word(0x90,777*64)+'&&(rom[0x8b]==255)')
    c.code([0x96,0x90],1)
    c.check('result read without status preserves CCF','rom[0x8b]==255')
    c.code([0x96,0x8b,0x96,0x90],2)
    c.check('status then result clears only matching CCF','(rom[0x8b]==254)&&((rom[0x86]&0x80)!=0)')
    c.setup(ctl2=0xc2)
    c.wait(40)
    c.check('sequence interrupt flag asserted','(rom[0x82]&1)==1')
    c.commands.append('dump /h rom 0x90 0x91\n')
    c.check('debugger inspection does not clear ADC flags','(rom[0x8b]==1)&&((rom[0x86]&0x80)!=0)')
    c.code([0x96,0x91],1)
    c.check('AFFC clears CCF/SCF/ASCIF','(rom[0x8b]==0)&&((rom[0x86]&0x80)==0)&&((rom[0x82]&1)==0)')
    c.setup(ctl2=0x82)
    c.wait(40)
    c.code([0x86,0x80,0x5a,0x86],2)
    c.check('SCF W1C also clears ASCIF','((rom[0x86]&0x80)==0)&&((rom[0x82]&1)==0)&&(rom[0x8b]==1)')
    c.setup()
    c.code([0x86,0,0x5a,0x82],2)
    c.wait(40)
    c.check('power off aborts conversion','rom[0x8b]==0')
    for reg in (0x83,0x84):
        c.setup()
        c.code([0x86,8 if reg==0x83 else 0,0x5a,reg],2)
        c.wait(40)
        c.check(f'control {reg:02x} abort does not restart','rom[0x8b]==0')
    c.setup(ctl3=0x0c,ctl5=0xa0) # one result, FIFO, continuous, right-justified
    c.wait(28*9)
    c.check('FIFO wraps and detects unread overwrite','(rom[0x8b]==255)&&((rom[0x86]&0x10)!=0)')
    c.code([0x86,0x10,0x5a,0x86],2)
    c.check('FIFO overrun W1C','(rom[0x86]&0x10)==0')
    c.setup(ctl3=8,ctl5=0xa0)
    c.wait(60)
    c.check('non-FIFO continuous unread overwrite','(rom[0x86]&0x10)!=0')
    c.code([0x86,8,0x5a,0x83],2)
    c.check('control abort preserves FIFOR','(rom[0x86]&0x10)!=0')
    c.code([0x86,0,0x5a,0x85],2)
    c.check('new sequence clears FIFOR and CCF','((rom[0x86]&0x10)==0)&&(rom[0x8b]==0)')
    c.setup(ctl5=0x80)
    c.commands.append('adc0=123\n')
    c.wait(7) # sample held at cycle 8; conversion finishes at cycle 28
    c.commands.append('adc0=999\n')
    c.wait(30)
    c.check('ADC holds sample during conversion',word(0x90,123))
    c.commands.append('adc0=1024\n')
    c.check('ADC input rejects out-of-range value','adc0==999')
    c.setup(ctl3=0) # zero length means eight conversions
    c.wait(250)
    c.check('zero sequence code means eight','rom[0x8b]==255')
    # GPIO reads direction-controlled pins; a disabled output doesn't drive input.
    c.commands.append('reset\nset memory xtboot_0_cfg 9 0xa5\n')
    c.code([0x86,0x5a,0x5a,0,0x86,0xf0,0x5a,2,0x96,0],5)
    c.check('GPIO input/latch/direction','A==0x55')
    c.code([0x86,0,0x5a,2,0x96,0],3)
    c.check('GPIO becomes externally driven input','A==0xa5')
    return c.run(executable,wsl,'peripherals.log')


def test_interrupts(executable,wsl):
    c=Checks()
    for cc in (0,0x40,0x80,0xd0,0xff):
        for mask in (0,0x10,0x40,0x80,0xff):
            c.commands.append(f'reset\nCC={cc}\n')
            c.code([0x14,mask],1)
            c.check(f'ORCC {cc:02x}|{mask:02x}',f'CC=={cc|(mask&~0x40)}')
    for vector,ie,flag in [(0xffca,0x66,0x67),(0xffd2,0x82,0x86)]:
        c.commands.append(f'reset\nset memory rom {vector} 0x11 0x00\nset memory rom {ie} {0x80 if ie==0x66 else 2}\nset memory rom {flag} 0x80\nCC=0xd0\nSP=0xff0\nIX=0x1234\nIY=0x5678\nD=0xabcd\n')
        c.code([0x10,0xef,0xa7,0xa7],1)
        c.check(f'IRQ {vector:04x} CLI deferral','(PC==0x1002)&&(SP==0xff0)')
        c.commands.append('step\n')
        expected=[0xc0,0xcd,0xab,0x12,0x34,0x56,0x78,0x10,0x03]
        c.check(f'IRQ {vector:04x} vector and frame','(PC==0x1100)&&(SP==0xfe7)&&(CC==0xd0)&&'+'&&'.join(f'(rom[{0xfe7+i}]=={v})' for i,v in enumerate(expected)))
        c.commands.append(f'set memory rom 0x1100 0x4c {flag} 0x80 0x0b\nstep 2\n')
        c.check(f'IRQ {vector:04x} RTI restores state','(PC==0x1003)&&(SP==0xff0)&&(CC==0xc0)&&(D==0xabcd)&&(IX==0x1234)&&(IY==0x5678)')
        c.commands.append(f'set memory rom {flag} 0x80\nstep\n')
        c.check(f'IRQ {vector:04x} second delivery','(PC==0x1100)&&(SP==0xfe7)')
    # Actual peripheral events, rather than debugger-injected status flags.
    c.setup(ctl2=0x82,ctl4=0x63)
    c.commands.append('set memory rom 0xffd2 0x11 0x00\nCC=0xc0\nbreak 0x1100\n')
    c.wait(500)
    c.check('ADC completion delivers IRQ','(PC==0x1100)&&(SP==0xfe7)&&((rom[0x86]&0x80)!=0)')
    c.commands.append('delete\nreset\nCC=0xd0\nSP=0xff0\nset memory rom 0xffca 0x11 0x00\nfill rom 0x1200 0x17ff 0xa7\n')
    c.code([0xcc,1,0,0x5c,0x76,0x86,0x84,0x5a,0x66,0x4c,0x66,8],5)
    c.commands.append('CC=0xc0\nbreak 0x1100\n')
    c.wait(500)
    c.check('modulus expiry delivers IRQ','(PC==0x1100)&&(SP==0xfe7)&&((rom[0x67]&0x80)!=0)')
    c.commands.append('delete\n')
    # Hardware priority is vector order unless HPRIO promotes a pending source.
    for highest,pc in [(0xf2,0x1100),(0xca,0x1200)]:
        c.commands.append(f'reset\nset memory rom 0xffd2 0x11 0x00\nset memory rom 0xffca 0x12 0x00\nset memory rom 0x82 2\nset memory rom 0x86 0x80\nset memory rom 0x66 0x80\nset memory rom 0x67 0x80\nset memory rom 0x1f {highest}\nCC=0\nSP=0xff0\n')
        c.code([0xa7],1)
        c.check(f'IRQ priority {highest:02x}',f'PC=={pc}')
    c.commands.append('reset\nCC=0\n')
    c.code([0x86,0xca,0x5a,0x1f],2)
    c.check('HPRIO write masked when interrupts enabled','rom[0x1f]==0xf2')
    c.commands.append('CC=0x10\n')
    c.code([0x86,0xcb,0x5a,0x1f],2)
    c.check('HPRIO write ignores reserved bit zero','rom[0x1f]==0xca')
    for old_x,new_x,expected in [(0,0x40,0),(0x40,0x40,0x40),(0x40,0,0)]:
        c.commands.append(f'reset\nCC={old_x}\nSP=0xfe7\nset memory rom 0xfe7 {new_x} 0xcd 0xab 0x12 0x34 0x56 0x78 0x12 0x00\n')
        c.code([0x0b],1)
        c.check(f'RTI X mask {old_x}/{new_x}',f'(CC=={expected})&&(PC==0x1200)&&(SP==0xff0)')
    return c.run(executable,wsl,'interrupts.log')


def test_firmware_adc(executable,wsl):
    images=['xt660-2004-2006-companion','xt660-5vk-1x-2008','xt660-2c1-10','xt660-2c1-10-immo-off','xt660-5vk-11']
    rows=[]
    for image in images:
        r,setup=prepare(image,wsl)
        _,data=registered_image(image)
        mem=bytes(r['base_address'])+data
        early=image==images[0]
        start,reader=(0x56d0,0x5728) if early else (0x4f31,0x4f52)
        assert mem[reader:reader+4]==bytes.fromhex('4e86800b')
        # Addresses are from each actual routine's STD operands, also asserted.
        outputs=[0xe3e+2*n for n in range(6)] if early else [0xed2+2*n for n in range(7)]+[0xee6]
        for n,address in enumerate(outputs):
            assert bytes([0xdc,0x90+2*n,0x7c,address>>8,address&255]) in mem[reader:reader+0x8c]
        c=Checks()
        c.commands.append(setup+'fill rom 0x800 0xfff 0\nset memory rom 0x82 0x80\nset memory rom 9 0x0c\nSP=0xff0\nCC=0xd0\nbreak 0x1006\n')
        for bank in range(1,5):
            values=[3,55,123,256,511,777,800+bank,1000+bank]
            for n,v in enumerate(values): c.commands.append(f'adc{n}={v}\n')
            c.code([0x16,start>>8,start&255,0x16,reader>>8,reader&255,0xa7],3000)
            expected=[word(address,values[n]*64) for n,address in enumerate(outputs)]
            if early:
                expected += [word(0xe4a+2*(bank%4),values[6]*64),word(0xe52+2*(bank%4),values[7]*64)]
            c.check(f'{image} sensor pass {bank}','(PC==0x1006)&&(SP==0xff0)&&'+'&&'.join(expected))
        c.commands.append('info hardware xtboot\n')
        count=c.run(executable,wsl,f'firmware-adc-{image}.log')
        rows.append({'image':image,'start':f'0x{start:04X}','reader':f'0x{reader:04X}','passes':count,'scope':'isolated unchanged firmware ADC routines; raw input fixtures, not full application boot'})
    return rows


def test_sensor_demo(executable,wsl):
    from sensors import sensor_demo
    inputs=[0,1,100,200,511,512,900,1023]
    rows=[]
    for image in ['xt660-2004-2006-companion','xt660-2c1-10']:
        report=sensor_demo(executable,image,inputs,wsl)
        expected=[v*64 for v in inputs]
        if image=='xt660-2004-2006-companion':
            expected=expected[:6]+[900*64]*4+[1023*64]*4
        assert list(report['ram_results'].values())==expected
        rows.append(image)
    for values in ([1]*7,[-1]+[0]*7,[1024]+[0]*7):
        try:
            sensor_demo(executable,rows[0],values,wsl)
            raise AssertionError('Invalid ADC inputs accepted')
        except ValueError:
            pass
    return {'images':rows,'invalid_inputs_rejected':3}
