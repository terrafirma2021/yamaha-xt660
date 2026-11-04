"""Flash-controller register checks and execution of the boot's RAM templates."""
from test_peripherals import Checks
from runner import execute, RUNS
from boot_service import BootService, frame


def test_flash_registers(executable,wsl):
    c=Checks()
    def setup(bank=1,protection=255):
        c.commands.append(f'set memory rom 0xff0c 255 {protection}\nreset\nCC=0xd0\nfill rom 0x1200 0x17ff 0xa7\nset memory xtboot_0_cfg 34 1\n')
        c.code([0x86,3,0x7a,1,0,0x86,bank,0x7a,1,3],4)
    def command(address,word,cmd):
        c.code([0xcc,word>>8,word&255,0x7c,address>>8,address&255,
                0x86,cmd,0x7a,1,6,0x86,128,0x7a,1,5],6)
    for bank,address in [(1,0x2000),(0,0x8000)]:
        setup(bank)
        c.commands.append(f'set memory rom {address} 255 255\n')
        command(address,0x1234,0x20)
        c.check(f'bank {bank} busy until program completes','(rom[0x105]&0xc0)==0')
        c.wait(40)
        c.check(f'bank {bank} word programmed',f'(rom[{address}]==0x12)&&(rom[{address+1}]==0x34)&&(rom[0x105]==0xc0)')
        command(address,0xffff,0x20);c.wait(40)
        c.check(f'bank {bank} cannot program zero to one',f'(rom[{address}]==0x12)&&(rom[{address+1}]==0x34)')
        c.commands.append(f'set memory rom {address+511} 0\nset memory rom {address+512} 42\n')
        command(address,0xffff,0x40);c.wait(1024)
        c.check(f'bank {bank} erase is exactly one 512-byte sector',f'(rom[{address}]==255)&&(rom[{address+511}]==255)&&(rom[{address+512}]==42)&&(rom[0x105]==0xc0)')
    setup(1)
    c.code([0x86,0x3f,0x7a,1,0],2)
    c.check('clock divisor is write once','rom[0x100]==0x83')
    c.commands.append('set memory rom 0x8000 0xab 0xcd\n')
    command(0x8000,0,0x20)
    c.check('wrong bank rejected without write','((rom[0x105]&16)!=0)&&(rom[0x8000]==0xab)&&(rom[0x8001]==0xcd)')
    c.code([0x86,0x30,0x7a,1,5],2)
    c.check('access errors clear through W1C','rom[0x105]==0xc0')
    setup(0,0x7f)
    c.commands.append('set memory rom 0x8000 0xab 0xcd\n')
    command(0x8000,0,0x20)
    c.check('protected flash rejected without write','((rom[0x105]&32)!=0)&&(rom[0x8000]==0xab)&&(rom[0x8001]==0xcd)')
    c.code([0x86,255,0x7a,1,4],2)
    c.check('software cannot remove protection','(rom[0x104]&128)==0')
    setup(1)
    c.code([0x86,0,0x7a,0x20,1],2)
    c.check('unaligned program word rejected','(rom[0x105]&16)!=0')
    count=c.run(executable,wsl,'flash-registers.log')
    script='set memory rom 0xff0c 255 255\nreset\nCC=0xd0\nset memory xtboot_0_cfg 34 1\n'
    script+='set memory rom 0x1000 0x86 3 0x7a 1 0 0x86 1 0x7a 1 3 0xcc 0xff 0xff 0x7c 0x20 0 0x86 0x40 0x7a 1 6 0x86 0x80 0x7a 1 5 0x06 0x20 0\npc 0x1000\nstep 20\ninfo hardware xtboot\nquit\n'
    out=execute(executable,script,wsl)
    (RUNS/'flash-busy-read.log').write_text(out,encoding='utf-8')
    assert 'busy flash bank' in out and 'FAULT=1' in out,out[-2000:]
    return count+1


def test_boot_programming(executable,wsl):
    image='xt660-2c1-10'
    with BootService(executable,image,wsl) as ecu:
        ecu.connect()
        for mode,size in enumerate((2,16,512,2048,256,1024)):
            assert ecu.read(0x8000,mode)==ecu.original[0x8000:0x8000+size]
        ecu.exchange(frame(5,1,bytes.fromhex('08205aa5')))
        reply=ecu.exchange(frame(9,0x80,ecu.original[0x8000:0x8800]),validate=False)
        assert reply==bytes.fromhex('09100005e2'),reply.hex()
    # A fresh session clears the hardware error left by the intentionally wrong bank.
    with BootService(executable,image,wsl) as ecu:
        ecu.connect();ecu.exchange(frame(5,1,bytes.fromhex('08205aa5')))
        ecu.exchange(frame(13))
        memory=ecu.flash()
        assert memory[:0xe000]==bytes([255])*0xe000
        assert memory[0xe000:]==ecu.original[0xf800:]
        for address in (0x1800,0x7800,0x8000,0xf000):
            expected=ecu.original[address:address+2048]
            ecu.program(address,expected,14)
            assert ecu.read(address,3)==expected,hex(address)
        assert ecu.flash()[0xe000:]==ecu.original[0xf800:]
        return dict(image=image,read_modes=6,bank_mismatch='09 rejected at 8000',
                    erase='0D erased 1800-F7FF; F800-FFFF unchanged',
                    ram_program_readback=['1800','7800','8000','F000'])
