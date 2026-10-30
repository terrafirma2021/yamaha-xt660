"""Selected CPU12 interlock paths. Synthetic inputs, not vehicle validation."""
import ast
import csv
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
tree=ast.parse((ROOT/'scripts/verify_protocol.py').read_text(encoding='utf-8'))
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='CPU')
cases=0
for im in json.loads((ROOT/'analysis/firmware/catalog.json').read_text())['images']:
    early=im['code_family']=='early';data=(ROOT/im['file']).read_bytes();rom=bytes(65536-len(data))+data
    path='analysis/disassembly.tsv' if early else 'analysis/firmware/families/late/disassembly.tsv'
    rows={int(r['address'],16):r for r in csv.DictReader((ROOT/path).open(encoding='utf-8'),delimiter='\t')}
    stand_start,stand_end,stand_set,config,ram_config,copy=(0xCC30,0xCC63,0xCC5E,0x4E6C,0xD57,0x5FFE) if early else (0xC296,0xC2C9,0xC2C4,0x4608,0xD8E,0x570B)
    fault19_start,fault19_end=(0x8B6F,0x8BEC) if early else (0x7F3F,0x7FBC)
    lean_config,lean_start,lean_end=(0x4E91,0xA8EA,0xA990) if early else (0x462D,0x9BAF,0x9C55)
    fault41_start,fault41_end=(0xBDFE,0xBE8A) if early else (0xB7C9,0xB855)
    ranges=[(stand_start,stand_end),(fault19_start,fault19_end),(lean_start,lean_end),(fault41_start,fault41_end)]
    for a,r in rows.items():
        if any(l<=a<h for l,h in ranges):
            raw=bytes.fromhex(r['bytes']);assert rom[a:a+len(raw)]==raw,(im['id'],hex(a))
    assert rom[config]==0 and rom[lean_config]==0
    assert rom[copy:copy+6]==bytes.fromhex('180c')+config.to_bytes(2,'big')+ram_config.to_bytes(2,'big')
    assert [a for a,r in rows.items() if r['instruction']=='BSET 0x88c,0x80']==[stand_set]
    ns={'ROM':rom,'ROWS':rows};exec(compile(ast.Module(body=[cls],type_ignores=[]),'<CPU12 interlocks>','exec'),ns);CPU=ns['CPU']
    patched=dict(rows);patched[stand_set]={**rows[stand_set],'bytes':'1d088c80','instruction':'BCLR 0x88c,0x80'}
    assert rom[stand_set:stand_set+4]==bytes.fromhex('1c088c80')
    # Both input levels, initial inhibit states and every counter value.
    for off in (False,True):
        ns['ROWS']=patched if off else rows
        for level in (0,1):
            for initial in (0,128):
                for count in range(256):
                    c=CPU();c.m[0x896 if early else 0x88F]=level if early else (0 if level else 0x40)
                    c.m[0xB07 if early else 0xB3E]=count;c.m[0xB08 if early else 0xB3F]=count;c.m[0x88C]=0x35|initial
                    c.run(stand_start,max_steps=40)
                    reached=min(count+1,255)>=rom[0x4BFD if early else 0x4225]
                    expected=(128 if level and not off else 0) if reached else initial
                    assert c.m[0x88C]==0x35|expected
                    cases+=1
    ns['ROWS']=rows
    # Fault-19 configuration skips creation/history without altering old bits.
    for flag in range(256):
        c=CPU();c.m[ram_config]=128
        current,history,dirty=(0x8AF,0x8B8,0xBD2) if early else (0x8B1,0x8BA,0xBF4)
        c.m[current]=flag;c.m[history]=flag^255
        c.run(fault19_start,stop=fault19_end,max_steps=30)
        assert c.m[current]==flag and c.m[history]==flag^255 and c.m[dirty]==0
        cases+=1
    # Enabled fault-19 positive control: unsafe input + starter request qualifies.
    c=CPU();c.m[0x896 if early else 0x88F]=1 if early else 0
    c.m[0x900 if early else 0x920]=255;c.m[0x880]=1
    c.m[0x8B6 if early else 0x8B8]=4;c.m[0xBC6 if early else 0xBE8]=255
    c.m[0xD8A if early else 0xDE6]=10
    c.run(fault19_start,stop=fault19_end,max_steps=100)
    assert c.m[current]&2 and c.m[history]&2
    # Master-off skips tip processing for every sensor byte. Latch clearing is
    # conditional on engine-state bit 881:20, so test and retain that limitation.
    for sample in range(256):
        for running in (0,0x20):
            c=CPU();c.m[lean_config]=128;c.m[0x8DD if early else 0x8E3]=sample
            c.m[0x884]=0xA3;c.m[0x885]=0xD5;c.m[0x881]=running
            c.run(lean_start,stop=lean_end,max_steps=30)
            assert c.m[0x884]==(0xA1 if running else 0xA0) and c.m[0x885]==0x55
            # Fault 41 is actively cleared by the master-off path; history stays.
            f41,h41,dirty=(0x8B1,0x8BA,0xBD2) if early else (0x8B3,0x8BC,0xBF4)
            c.m[f41]=0xB5;c.m[h41]=0x5A
            c.run(fault41_start,stop=fault41_end,max_steps=40)
            assert c.m[f41]==0xA5 and c.m[h41]==0x5A and c.m[dirty]&0x20
            cases+=1
    # Enabled tilt and sensor-disconnect positive controls.
    c=CPU();c.m[0x8DD if early else 0x8E3]=rom[0x4E93 if early else 0x462F]
    c.put(hex(0xB0A if early else 0xB42),65535,16);c.m[0xBC8 if early else 0xBEA]=255
    c.run(lean_start,stop=lean_end,max_steps=100)
    assert c.m[0x885]&0x80 and c.m[0x884]&1
    c=CPU();c.m[0x8DD if early else 0x8E3]=0
    c.m[0x8B6 if early else 0x8B8]=8;c.m[0xB0C if early else 0xB44]=255;c.m[0xD8A if early else 0xDE6]=10
    c.run(fault41_start,stop=fault41_end,max_steps=100)
    assert c.m[f41]&0x10 and c.m[h41]&0x10
    print(im['id']+': sidestand, fault 19, tip-over and fault 41 paths passed')
print(f'{cases:,} selected-path cases passed; external relays, wiring and hardware are not simulated.')
