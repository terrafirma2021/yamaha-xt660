"""Independent byte execution of the stateless dashboard pulse-offset patch.

Selected CPU12 instructions only; not a complete ECU/peripheral emulator.
"""
import csv
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fixtures = json.loads(subprocess.check_output(['node', '--input-type=module', '-e', """
import {speedLayouts,speedRecipe} from './site/assets/tools-speed.mjs';
console.log(JSON.stringify(Object.entries(speedLayouts).map(([code_family,layout])=>({
 code_family,layout,cases:[true,false].flatMap(enabled=>Array.from({length:41},(_,i)=>({
 enabled,offset:i-20,recipe:speedRecipe({code_family},enabled,i-20)
 }))) }))));
"""], cwd=ROOT, text=True))
catalog = json.loads((ROOT/'analysis/firmware/catalog.json').read_text())


class CPU:
    def __init__(self, memory):
        self.m = bytearray(memory)
        self.a, self.b, self.x, self.y, self.cc = 0x73, 0xC3, 0xBEEF, 0x1968, 0
        self.sp = 0x0F80
        self.writes = set()

    def put(self, a, v):
        self.m[a] = v
        self.writes.add(a)

    def push(self, v):
        self.sp -= 1
        self.put(self.sp, v)

    def pop(self):
        v = self.m[self.sp]
        self.sp += 1
        return v

    def nzv(self, value):
        self.cc = (self.cc & ~14) | (4 if value == 0 else 0) | (8 if value & 128 else 0)

    def interrupt(self):
        # Model CPU12 interrupt save/restore and an unrelated pulse-counter tick.
        # It cannot publish the reply while its ready bit remains clear.
        saved = [0x12, 0x34, self.y >> 8, self.y & 255, self.x >> 8,
                 self.x & 255, self.a, self.b, self.cc]
        for v in saved:
            self.push(v)
        for v in reversed(saved):
            assert self.pop() == v

    def run(self, pc, stop, interrupt_at=-1):
        for step in range(60):
            if pc == stop:
                return
            if step == interrupt_at:
                self.interrupt()
            op = self.m[pc]
            pc += 1
            if op in (0x16, 0xB6, 0x7A, 0xBB):
                addr = self.m[pc]*256+self.m[pc+1]
                pc += 2
                if op == 0x16:  # JSR extended
                    self.push(pc & 255)
                    self.push(pc >> 8)
                    pc = addr
                elif op == 0xB6:
                    self.a = self.m[addr]
                    self.nzv(self.a)
                elif op == 0x7A:
                    self.put(addr, self.a)
                    self.nzv(self.a)
                else:
                    result = self.a+self.m[addr]
                    self.cc = (self.cc & ~1) | int(result > 255)
                    self.a = result & 255
                    self.nzv(self.a)
            elif op == 0x39:
                self.push(self.cc)
            elif op == 0x38:
                self.cc = self.pop()
            elif op == 0x3D:
                pc = self.pop()*256+self.pop()
            elif op in (0x86, 0x8B):
                value = self.m[pc]
                pc += 1
                if op == 0x86:
                    self.a = value
                else:
                    result = self.a+value
                    self.cc = (self.cc & ~1) | int(result > 255)
                    self.a = result & 255
                self.nzv(self.a)
            elif op in (0x27, 0x24, 0x25):
                rel = self.m[pc]
                pc += 1
                take = bool(self.cc & 4) if op == 0x27 else bool(self.cc & 1) == (op == 0x25)
                if take:
                    pc += rel if rel < 128 else rel-256
            else:
                raise AssertionError(f'Unexpected opcode {op:02X} at {pc-1:04X}')
        raise AssertionError('Patch did not return within instruction bound')


checks = 0
for family in fixtures:
    f = family['layout']
    early = family['code_family'] == 'early'
    stem = ROOT/('analysis' if early else 'analysis/firmware/families/late')
    rows = list(csv.DictReader((stem/'disassembly.tsv').open(), delimiter='\t'))
    cave = set(range(f['cave'], f['cave']+24))
    for r in rows:
        a = int(r['address'], 16)
        assert not cave.intersection(range(a, a+len(bytes.fromhex(r['bytes']))))
        assert not cave.intersection(int(v,16) for v in re.findall(r'0x([a-f0-9]+)',r['instruction']))
    for r in csv.DictReader((stem/'references.tsv').open(), delimiter='\t'):
        # Export header uses from/to, inspect values without depending on labels.
        assert int(list(r.values())[1],16) not in cave
    for image in (i for i in catalog['images'] if i['code_family'] == family['code_family']):
        data = (ROOT/image['file']).read_bytes()
        rom = bytes(image['base_address'])+data
        assert rom[f['cave']:f['cave']+24] == bytes([255])*24
        assert rom[f['hook']:f['hook']+6] == bytes([0xB6,f['raw']>>8,f['raw']&255,0x7A,f['output']>>8,f['output']&255])
        # Ready is published only after the constructor returns; checked in each BIN.
        gate = 0x6299 if early else 0x5A5B
        flag = 0x08AE if early else 0x08B0
        constructor = 0x62AA if early else 0x5A6C
        expected = bytes([0x1F,flag>>8,flag&255,2,11,0x16,constructor>>8,constructor&255,
                          0x1D,flag>>8,flag&255,2,0x1C,flag>>8,flag&255,1,0x3D])
        assert rom[gate:gate+len(expected)] == expected
        for case in family['cases']:
            patched = bytearray(rom)
            for p in case['recipe']:
                patched[p['address']:p['address']+len(p['bytes'])] = bytes(p['bytes'])
            for count in range(256):
                for cc in (0xA1, 0x50):
                    c = CPU(patched)
                    c.cc = cc
                    c.m[f['raw']] = count
                    c.run(f['hook'],f['hook']+6)
                    expected = 0 if not case['enabled'] or count == 0 else max(0,min(255,count+case['offset']))
                    assert c.a == c.m[f['output']] == expected
                    assert c.m[f['raw']] == count
                    assert (c.b,c.x,c.y,c.sp) == (0xC3,0xBEEF,0x1968,0xF80)
                    assert c.cc == (cc & ~14) | (4 if expected == 0 else 0) | (8 if expected & 128 else 0)
                    assert c.writes <= {f['output'],0xF7D,0xF7E,0xF7F}
                    # Run the actual stock checksum tail with the edited speed byte.
                    first = f['output']-1
                    c.m[first],c.m[first+2],c.a = 199,129,254
                    tail = 0x6486 if early else 0x5C4B
                    c.run(tail,tail+15)
                    assert list(c.m[first:first+5]) == [199,expected,129,254,(199+expected+129+254)&255]
                    checks += 1
            # Interrupt save/restore at every position, including inside the stub.
            for count in (0,1,19,20,21,235,254,255):
                for step in range(15):
                    c = CPU(patched);c.m[f['raw']] = count
                    c.run(f['hook'],f['hook']+6,step)
                    expected = 0 if not case['enabled'] or count == 0 else max(0,min(255,count+case['offset']))
                    assert c.m[f['output']] == expected and c.sp == 0xF80
                    checks += 1
print(f'Speed patch: {checks:,} byte-executed cases across nine BINs; bounds, stationary zero, flags/registers, stack balance, reply checksum and interrupt save/restore passed. Hardware untested.')
