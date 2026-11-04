"""Independent SCI register semantics and observed external storage transactions."""
from test_peripherals import Checks
from storage import factory_storage
from runner import execute, RUNS
import re


def test_transfer_and_disassembly(executable,wsl):
    c=Checks()
    for old in (0,0x40):
        for value in (0,0x40,0xff,0xbf):
            expected=value if old else value&~0x40
            for post in (0x02,0x82,0xa0):
                c.commands.append(f'reset\nCC={old}\nA={value}\n')
                c.code([0xb7,post],1)
                c.check(f'TFR/EXG X-mask {old}/{value}/{post}',f'(CC=={expected})'+(f'&&(A=={old})' if post&128 else ''))
    count=c.run(executable,wsl,'transfer-x-mask.log')
    cases=[
        ('1800301234',r'MOVW\s+#\$1234, \+1,X\+'),
        ('1801301200',r'MOVW\s+\$1200, \+1,X\+'),
        ('18023171',r'MOVW\s+\+2,X\+, \+2,Y\+'),
        ('180312341200',r'MOVW\s+#\$1234, \$1200'),
        ('180412001400',r'MOVW\s+\$1200, \$1400'),
        ('1805311200',r'MOVW\s+\+2,X\+, \$1200'),
        ('18083056',r'MOVB\s+#\$56, \+1,X\+'),
        ('1809301200',r'MOVB\s+\$1200, \+1,X\+'),
        ('180a3070',r'MOVB\s+\+1,X\+, \+1,Y\+'),
        ('180b561200',r'MOVB\s+#\$56, \$1200'),
        ('180c12001400',r'MOVB\s+\$1200, \$1400'),
        ('180d301200',r'MOVB\s+\+1,X\+, \$1200')]
    commands='reset\nIX=0x1200\nIY=0x1400\n'
    for code,_ in cases:
        commands+='set memory rom 0x1000 '+' '.join(str(v) for v in bytes.fromhex(code))+'\ndc 0x1000 0x1000\n'
    commands+='expression /X (0x66000000+((IX==0x1200)&&(IY==0x1400)))\nquit\n'
    out=execute(executable,commands,wsl)
    (RUNS/'move-disassembly.log').write_text(out,encoding='utf-8')
    for _,pattern in cases:
        assert re.search(pattern,out,re.I),pattern+'\n'+out
    assert '0x66000001' in out
    return dict(transfer_checks=count,mov_disassembly=len(cases),disassembly_registers_unchanged=True)


def test_load_store_flags(executable,wsl):
    c=Checks()
    c.commands.append('reset\n')
    for flags in (0xd0,0xff):
        for value in range(256):
            expected=(flags&~14)|(4 if value==0 else 0)|(8 if value&128 else 0)
            for opcode,register in [(0x86,'A'),(0xc6,'B')]:
                c.commands.append(f'CC={flags}\n')
                c.code([opcode,value],1)
                c.check(f'load {register} {value} flags {flags}',f'({register}=={value})&&(CC=={expected})')
            c.commands.append(f'A={value}\nCC={flags}\n')
            c.code([0x7a,0x11,0x00],1)
            c.check(f'store A {value} flags {flags}',f'(rom[0x1100]=={value})&&(CC=={expected})')
        for value in (0,1,0x7fff,0x8000,0xffff):
            expected=(flags&~14)|(4 if value==0 else 0)|(8 if value&32768 else 0)
            for opcode,register in [(0xcc,'D'),(0xce,'IX'),(0xcd,'IY'),(0xcf,'SP')]:
                c.commands.append(f'CC={flags}\n')
                c.code([opcode,value>>8,value&255],1)
                c.check(f'load16 {register} {value} flags {flags}',f'({register}=={value})&&(CC=={expected})')
            c.commands.append(f'D={value}\nCC={flags}\n')
            c.code([0x7c,0x11,0],1)
            c.check(f'store16 D {value} flags {flags}',f'(rom[0x1100]*256+rom[0x1101]=={value})&&(CC=={expected})')
    return c.run(executable,wsl,'load-store-flags.log')


def test_move_updates(executable,wsl):
    c=Checks();c.commands.append('reset\n')
    for size,opcode in [(1,0x0a),(2,0x02)]:
        for pre in (False,True):
            for delta in (-8,-2,-1,1,2,8):
                for reg,bits in [('IX',0),('IY',64),('SP',128)]:
                    # MOVB/W indexed -> extended; register update is part of execution,
                    # whereas disassembly must leave it untouched.
                    post=bits|0x20|(0 if pre else 0x10)|((delta if delta<0 else delta-1)&15)
                    address=0x1400+(delta if pre else 0)
                    c.commands.append(f'{reg}=0x1400\nCC=0xff\nset memory rom {address} 0x81 0x7e\n')
                    c.code([0x18,0x0d if size==1 else 0x05,post,0x11,0],1)
                    c.check(f'MOV{size} {reg} pre={pre} delta={delta}',f'({reg}=={0x1400+delta})&&(rom[0x1100]==0x81)&&(CC==255)'+('&&(rom[0x1101]==0x7e)' if size==2 else ''))
                    c.commands.append('IX=0x1400\nIY=0x1500\nCC=0xff\nset memory rom 0x1400 0x12 0x34\n')
                    c.code([0x18,opcode,0x30+(size-1),0x70+(size-1)],1)
                    c.check(f'MOV{size} both post updates {reg} {delta}',f'(IX=={0x1400+size})&&(IY=={0x1500+size})&&(rom[0x1500]==0x12)&&(CC==255)'+('&&(rom[0x1501]==0x34)' if size==2 else ''))
    return c.run(executable,wsl,'move-updates.log')


def test_serial(executable,wsl):
    c=Checks()
    def reset(n=0, divisor=1, control=12):
        c.commands.append('reset\nCC=0xd0\nSP=0xff0\nfill rom 0x1200 0x7fff 0xa7\n')
        c.commands.append(f'set memory rom {0xc8+n*8} 0 {divisor} 0 {control}\nset memory xtboot_0_cfg {28+n} {divisor}\n')
    for n in (0,1):
        base=0xc8+n*8
        for divisor in (1,2,10):
            reset(n,divisor)
            c.code([0x86,0x52,0x5a,base+7],2)
            c.wait(divisor*160)
            c.check(f'SCI{n} qualified TX required div {divisor}',f'xtboot_0_cfg[{30+n}]==0')
            c.code([0x96,base+4,0x86,0x52,0x5a,base+7],3)
            c.wait(divisor*160-3)
            c.check(f'SCI{n} TX not early div {divisor}',f'(xtboot_0_cfg[{30+n}]==0)&&((rom[{base+4}]&64)==0)')
            c.wait(1)
            c.check(f'SCI{n} TX complete div {divisor}',f'(xtboot_0_cfg[{30+n}]==1)&&(xtboot_0_cfg[{32+n}]==0x52)&&((rom[{base+4}]&0xc0)==0xc0)')
            c.commands.append(f'set memory xtboot_0_cfg {26+n} 0xa9\n')
            c.wait(divisor*160-1)
            c.check(f'SCI{n} RX not early div {divisor}',f'(rom[{base+4}]&32)==0')
            c.wait(1)
            c.check(f'SCI{n} RX complete div {divisor}',f'((rom[{base+4}]&32)!=0)&&(rom[{base+7}]==0xa9)')
            c.code([0x96,base+7],1)
            c.check(f'SCI{n} RX unqualified read keeps flag',f'(rom[{base+4}]&32)!=0')
            c.code([0x96,base+4,0x96,base+7],2)
            c.check(f'SCI{n} RX status/data clears flag',f'(A==0xa9)&&((rom[{base+4}]&32)==0)')
        reset(n)
        c.code([0x96,base+4,0x86,0x11,0x5a,base+7,0x96,base+4,0x86,0x22,0x5a,base+7],6)
        c.check(f'SCI{n} queued TX holds TDRE low',f'(rom[{base+4}]&128)==0')
        c.wait(320)
        c.check(f'SCI{n} TX queue order',f'(xtboot_0_cfg[{30+n}]==2)&&(xtboot_0_cfg[{32+n}]==0x22)')
        reset(n)
        c.commands.append(f'set memory xtboot_0_cfg {26+n} 0x55\nset memory xtboot_0_cfg {26+n} 0xaa\n')
        c.wait(320)
        c.check(f'SCI{n} overrun retains first byte',f'(rom[{base+7}]==0x55)&&((rom[{base+4}]&40)==40)')
        c.code([0x96,base+4,0x96,base+7],2)
        c.check(f'SCI{n} overrun acknowledge',f'(rom[{base+4}]&40)==0')
        c.wait(160)
        c.check(f'SCI{n} idle after reception',f'(rom[{base+4}]&16)!=0')
        c.code([0x96,base+4,0x96,base+7],2)
        c.wait(500)
        c.check(f'SCI{n} idle does not repeat until new byte',f'(rom[{base+4}]&16)==0')
        reset(n,control=0)
        c.commands.append(f'set memory xtboot_0_cfg {26+n} 0x99\n')
        c.wait(160)
        c.check(f'SCI{n} disabled receiver ignores traffic',f'(rom[{base+4}]&32)==0')
        reset(n)
        c.code([0x86,6,0x5a,base+3],2)
        c.wait(160)
        c.check(f'SCI{n} idle wakes RWU',f'((rom[{base+3}]&2)==0)&&((rom[{base+4}]&16)==0)')
        reset(n)
        c.commands.append(f'set memory xtboot_0_cfg {28+n} 2\nset memory xtboot_0_cfg {26+n} 0x44\n')
        c.wait(320)
        c.check(f'SCI{n} baud mismatch framing flag',f'(rom[{base+4}]&34)==34')
        reset(n,control=0x24)
        vector=0xffd4 if n else 0xffd6
        c.commands.append(f'set memory rom {vector} 0x11 0\nset memory xtboot_0_cfg {26+n} 1\nCC=0\nbreak 0x1100\n')
        c.wait(200)
        c.check(f'SCI{n} receive IRQ vector',f'(PC==0x1100)&&(SP==0xfe7)')
        c.commands.append('delete\n')
    return c.run(executable,wsl,'serial-registers.log')


def test_storage(executable,wsl):
    c=Checks()
    c.commands.append('reset\nCC=0xd0\nSP=0xff0\nfill rom 0x1200 0x7fff 0xa7\nfill eeprom 0 511 255\nset memory xtboot_0_cfg 18 2\nset memory rom 0xd8 0x50\n')
    def select(on):
        c.code([0x86,8 if on else 0,0x5a,0xf0],2)
    def transfer(value):
        c.code([0x96,0xdb,0x96,0xdd,0x86,value,0x5a,0xdd],4)
        c.wait(16)
    def command(values):
        select(True)
        for value in values: transfer(value)
        select(False)
    command([0x0a,0x31,0x69])
    c.check('storage write requires EWEN','eeprom[0x31]==255')
    command([9,0x80])
    command([0x0a,0x31,0x69])
    c.check('storage write commits on CS release','eeprom[0x31]==0x69')
    select(True)
    c.code([0x96,0xe9],1)
    c.check('storage busy drives MISO low','(A&16)==0')
    c.wait(1024)
    c.code([0x96,0xe9],1)
    c.check('storage ready drives MISO high','(A&16)!=0')
    select(False)
    select(True)
    for value in [0x0c,0x31,0xff]: transfer(value)
    c.code([0x96,0xdb,0x96,0xdd],2)
    c.check('storage command reads written byte','A==0x69')
    select(False)
    c.commands.append('reset\n')
    c.check('storage survives MCU reset','eeprom[0x31]==0x69')
    count=c.run(executable,wsl,'storage-registers.log')
    results=[]
    for image in ['xt660-2004-2006-companion','xt660-5vk-1x-2008','xt660-2c1-10','xt660-2c1-10-immo-off','xt660-5vk-11']:
        data,meta=factory_storage(executable,image,wsl)
        expected=bytearray([255]*512)
        expected[:10]=bytes.fromhex('80808080808000010001')
        expected[16:32]=bytes([128]*16)
        expected[32:41]=bytes(9)
        expected[48]=0
        assert data==expected,image
        results.append(dict(image=image,**meta))
    return dict(register_checks=count,firmware_initializers=results)
