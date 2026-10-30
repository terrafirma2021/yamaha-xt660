"""Execute selected, byte-checked CPU12 paths; not a hardware qualification.

Reuses only the interpreter class, without running the protocol test module.
Exercises every 8-bit coolant value, active/inactive cut, and speed boundaries.
"""
import ast
import csv
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT/'scripts/verify_protocol.py').read_text(encoding='utf-8'))
cpu_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'CPU')
catalog = json.loads((ROOT/'analysis/firmware/catalog.json').read_text(encoding='utf-8'))
# Exercise the exact byte recipe shipped to the browser, then independently
# decode each replacement as a CPU12 extended JMP (06, high, low).
recipes=json.loads(subprocess.check_output(['node','--input-type=module','-e',
    "import {featureDefinitions} from './site/assets/tools-features.mjs'; console.log(JSON.stringify(Object.fromEntries(['early','late'].map(code_family=>[code_family,featureDefinitions({code_family}).find(f=>f.id==='overrun')]))));"],cwd=ROOT,text=True))
checks = 0
for image in catalog['images']:
    early = image['code_family'] == 'early'
    data = (ROOT/image['file']).read_bytes()
    rom = bytes(65536-len(data)) + data
    path = 'analysis/disassembly.tsv' if early else 'analysis/firmware/families/late/disassembly.tsv'
    rows = {int(r['address'],16):r for r in csv.DictReader((ROOT/path).open(encoding='utf-8'),delimiter='\t')}
    start, stop = (0x765D,0x77B1) if early else (0x6E6B,0x6FC6)
    for a,r in rows.items():
        if start <= a < stop:
            raw=bytes.fromhex(r['bytes'])
            assert rom[a:a+len(raw)] == raw, (image['id'],hex(a))
    ns={'ROM':rom,'ROWS':rows}
    exec(compile(ast.Module(body=[cpu_class],type_ignores=[]),'<CPU12 selected-path interpreter>','exec'),ns)
    CPU=ns['CPU']
    recipe=recipes[image['code_family']]
    sites=[(0x765D,0x777A),(0x778D,0x77A2)] if early else [(0x6E6B,0x6F8F),(0x6FA2,0x6FB7)]
    assert [p['address'] for p in recipe['bytes']]==[a+i for a,_ in sites for i in range(3)]
    patch_rom=bytearray(rom)
    for p in recipe['bytes']:
        assert rom[p['address']]==p['on']
        patch_rom[p['address']]=p['off']
    patched=dict(rows)
    for a,target in sites:
        assert len(bytes.fromhex(rows[a]['bytes']))==3
        raw=patch_rom[a:a+3]
        assert raw[0]==6 and int.from_bytes(raw[1:],'big')==target
        assert target in rows
        patched[a]={**rows[a],'bytes':raw.hex(),'instruction':f'JMP {hex(target)}'}
    for p in recipe['legacy']: assert patch_rom[p['address']]==rom[p['address']]==p['on']
    # Positive control: stock parameters really reach the cut path.
    c=CPU()
    c.m[0x8F4 if early else 0x914]=200
    c.m[0xAFA if early else 0xB2D]=255
    c.m[0x900 if early else 0x920]=100
    c.m[0x88D]=4;c.m[0x886]=0x10
    c.m[0xB16 if early else 0xB4E]=255
    c.m[0xB17 if early else 0xB4F]=255
    c.m[0xD87]=9;c.m[0x896]=0x10
    c.run(start,stop=stop,max_steps=200)
    assert c.m[0x886]&0x40 and c.m[0x97A]==0, image['id']
    ns['ROWS']=patched
    ns['ROM']=bytes(patch_rom)
    for temp in range(256):
        for active in (False,True):
            for speed in (0,23,24,54,55,60,61,255):
                c=CPU()
                c.m[0x8F4 if early else 0x914]=temp
                c.m[0x900 if early else 0x920]=speed
                c.m[0xAFA if early else 0xB2D]=255
                c.m[0x886]=0xD9 if active else 0x99
                c.m[0x97A]=0
                c.m[0x88D]=4;c.m[0x896]=0x10
                c.m[0x88C]=0xA5 # unrelated cut flags must survive
                c.run(start,stop=stop,max_steps=200)
                assert c.m[0x886]&0xC1==0x81 # clears only decel in this mask
                assert c.m[0x97A]==128 and c.m[0x88C]==0xA5
                checks+=1
    # All shared flag patterns; both throttle-latch states; old multiplier values.
    # This also starts with an already-active cut and non-neutral ignition trim.
    for flags in range(256):
        for multiplier in (0,1,64,127,128,129,254,255):
            for throttle in (0,4):
                c=CPU();c.m[0x886]=flags;c.m[0x88A]=255;c.m[0x88D]=throttle
                c.m[0x97A]=multiplier;c.m[0x88C]=flags^255
                spark=0xA86 if early else 0xA8E
                c.m[spark]=73
                c.m[0x8F4 if early else 0x914]=flags
                c.m[0x900 if early else 0x920]=255-flags
                c.m[0xAFA if early else 0xB2D]=flags
                c.m[0x896]=flags;c.m[0x88F]=flags
                # Deliberately vary the old thresholds: bypass must not depend on them.
                for p in recipe['legacy']: c.m[p['address']]=flags
                c.run(start,stop=stop,max_steps=40)
                assert c.m[0x886]==flags&~0x58 and c.m[0x88A]==0
                assert c.m[0x97A]==128 and c.m[0x88C]==flags^255
                assert c.m[0x88D]==throttle and c.m[spark]==73
                assert c.m[0xB16 if early else 0xB4E]==0
                checks+=1
    ns['ROWS']=rows;ns['ROM']=rom
    # PAIR: replace both normal and diagnostic assert instructions with clear.
    pair,mask=([0x9D5A,0xBAC3],2) if early else ([0x91EF,0xA465],1)
    writers=[a for a,r in rows.items() if r['instruction'].startswith('BSET 0x00f0,') and int(r['instruction'].split(',')[-1],0)&mask]
    assert writers==pair, writers
    init=0x5033 if early else 0x4828
    assert rom[init:init+4]==bytes([0xC6,0xE0 if early else 0xA0,0x5B,0xF0])
    assert not rom[init+1]&mask
    for a in pair:
        assert rom[a:a+3]==bytes([0x4C,0xF0,mask])
        patched=dict(rows)
        patched[a]={**rows[a],'bytes':bytes([0x4D,0xF0,mask]).hex(),'instruction':f'BCLR 0x00f0,0x{mask:x}'}
        ns['ROWS']=patched
        for port in range(256):
            c=CPU();c.m[0xF0]=port;c.run(a,stop=a+3)
            assert c.m[0xF0]==port&~mask
            checks+=1
    ns['ROWS']=rows
    # Auth gate: disabled bypasses challenge; enabled with pending auth enters it.
    config,entry,bypass,auth=(0xDD5,0xA9AF,0xAA51,0xA9BF) if early else (0xE4D,0x9CF1,0x9D93,0x9D01)
    for a,r in rows.items():
        if entry<=a<=auth:
            raw=bytes.fromhex(r['bytes']);assert rom[a:a+len(raw)]==raw
    copy=0x61DE if early else 0x58DF
    source=0x4E7D if early else 0x4619
    assert rom[copy:copy+6]==bytes.fromhex('180c')+source.to_bytes(2,'big')+config.to_bytes(2,'big')
    for value in (0,128):
        c=CPU();c.m[config]=value
        c.m[0xD06 if early else 0xD1F]=2
        c.run(entry,stop=bypass if value==128 else auth,max_steps=12)
        checks+=1
    print(image['id']+': cut, PAIR and immobilizer paths passed')
print(f'{checks:,} selected-path cases passed; ECU hardware and timing not tested.')
