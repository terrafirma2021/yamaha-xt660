"""Byte-checked O2 gates, fault creation and serial report tests. No ECU I/O."""
import ast
import csv
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
tree=ast.parse((ROOT/'scripts/verify_protocol.py').read_text(encoding='utf-8'))
cpu_class=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='CPU')
catalog=json.loads((ROOT/'analysis/firmware/catalog.json').read_text(encoding='utf-8'))
cases=0
for image in catalog['images']:
    data=(ROOT/image['file']).read_bytes();rom=bytes(65536-len(data))+data
    early=image['code_family']=='early'
    path='analysis/disassembly.tsv' if early else 'analysis/firmware/families/late/disassembly.tsv'
    rows={int(r['address'],16):r for r in csv.DictReader((ROOT/path).open(encoding='utf-8'),delimiter='\t')}
    # Include all instructions executed below, including scanner/serial helpers.
    ranges=[(0xEE78,0xEF6D),(0xF4DA,0xF4E0)] if early else [(0x5B14,0x5CD0),(0x5EA1,0x5EF1),(0x6405,0x64BA),(0x9800,0x98CB),(0x9944,0x9AB4),(0xE8FE,0xEA25),(0xF25B,0xF261)]
    for a,r in rows.items():
        if any(lo<=a<hi for lo,hi in ranges):
            raw=bytes.fromhex(r['bytes']);assert rom[a:a+len(raw)]==raw,(image['id'],hex(a))
    ns={'ROM':rom,'ROWS':rows}
    exec(compile(ast.Module(body=[cpu_class],type_ignores=[]),'<CPU12 O2 tests>','exec'),ns)
    CPU=ns['CPU']
    # Same overrun bit suppresses injection, but is NOT a normal coil-charge gate.
    for active in (0,0x40):
        c=CPU();c.m[0x886]=active
        c.run(0xF4DA if early else 0xF25B,stop=(0xF4DF if early else 0xF260) if active else (0xF4E0 if early else 0xF261))
        c=CPU();c.m[0x886]=active
        c.m[0xC04 if early else 0xC26]=5;c.m[0x925 if early else 0x945]=5
        c.put(hex(0xAF0 if early else 0xB22),1000,16)
        c.put(hex(0xAA2 if early else 0xAA8),200,16)
        c.run(0xEE78 if early else 0xE8FE,max_steps=100)
        assert c.val('0x56',16)==1200 and c.m[0x49]&0xC0==0xC0
        cases+=1
    if early:
        assert rom[0x18D3]==9
        assert set(rom[0x35B0:0x3614])=={0} and set(rom[0x363C:0x36A0])=={0}
        print(image['id']+': no configured O2 feedback; injection/coil distinction passed')
        continue
    assert rom[0x368E]==128
    consumers=[a for a,r in rows.items() if '0x368e' in r['instruction']]
    assert consumers==[0x6410,0x9800,0x99D5,0x9A48]
    assert [rom[a] for a in (0x46A1,0x46A3,0x46A4)]==[24,31,32]
    # Positive control: the enabled path creates current + historical fault 24.
    c=CPU();c.m[0x914]=255;c.put('0x920',65535,16);c.put('0x8f2',65535,16)
    c.m[0xB7A]=255;c.m[0x8B8]=0x40
    c.run(0x6405,stop=0x64B0,max_steps=100)
    assert c.m[0x8B2]&0x10 and c.m[0x8BB]&0x10 and c.m[0xBF4]&0x44==0x44
    # Positive controls for the two trim-limit faults, regardless of their
    # separately configured diagnostic inhibit flags in the stock BIN.
    for entry,stop,flag,counter,gain in [(0x99CE,0x9A41,4,0xB7B,0xCCCC),(0x9A41,0x9AB4,2,0xB7C,0x3333)]:
        c=CPU();c.m[0x99F]=0x80;c.m[0x8B8]=0x30;c.m[counter]=255;c.put('0x97c',gain,16)
        c.run(entry,stop=stop,max_steps=100)
        assert c.m[0x8B2]&flag and c.m[0x8BB]&flag
    for value in range(256):
        # Off bypasses detection before it can create or log a fault. Preserve
        # existing bits to make the limit explicit: this is not history erasure.
        for entry,stop in [(0x6405,0x64B0),(0x99CE,0x9A41),(0x9A41,0x9AB4)]:
            c=CPU();c.m[0x368E]=0;c.m[0x914]=value;c.m[0x99F]=value
            c.m[0x8B2]=value;c.m[0x8BB]=value^255;c.m[0x8B8]=255
            c.m[0xB7A:0xB7D]=bytes([255]*3)
            c.run(entry,stop=stop,max_steps=100)
            assert c.m[0x8B2]==value and c.m[0x8BB]==value^255 and c.m[0xBF4]==0
            cases+=1
        c=CPU();c.m[0x368E]=0;c.m[0x99F]=value;c.m[0x9AB]=255
        c.run(0x9800,stop=0x98CB,max_steps=30)
        assert c.m[0x99F]==value&0x7F and c.m[0x9AB]==0
        for old in (0,0x3332,0x3333,0x7FFF,0x8000,0x8001,0xCCCC,0xFFFF):
            c.put('0x97c',old,16);c.run(0x9944,stop=0x99CE,max_steps=40)
            assert c.val('0x97c',16)==0x8000
            cases+=1
    # Feed a single current fault through the actual scan and normal serial
    # reply builder. A pre-existing fault still reports even with O2 disabled.
    for config in (0,128):
        for flag,code in ((0,0),(0x10,24),(4,31),(2,32)):
            c=CPU();c.m[0x368E]=config;c.m[0x8B2]=flag;c.m[0x8A3]=2
            c.m[0x893]=0x40;c.m[0x881]=0x20
            c.run(0x5B14,max_steps=800)
            assert c.m[0x8AA]&0x3F==code
            assert c.m[0x8AC]==sum(c.m[0x8A8:0x8AC])&255
            cases+=1
    print(image['id']+': O2 gates, neutral correction, fault logging and serial reply passed')
print(f'{cases:,} O2/overrun selected-path cases passed; no hardware validation.')
