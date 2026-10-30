"""Execute the actual CO lookup and both fuel lanes for every registered BIN.

Uses the existing CPU12 p-code reference runner, not a native runtime dependency.
No firmware files are written. Physical clock/crank scaling is not asserted.
"""
import csv,json,subprocess
from test_firmware_lookups import ROOT,load_code,reference,put,rd

recipes=json.loads(subprocess.check_output(['node','--input-type=module','-e',
    "import {coLayouts,coDefinition} from './site/assets/tools-co.mjs'; console.log(JSON.stringify(Object.fromEntries(Object.entries(coLayouts).map(([code_family,l])=>[code_family,{...l,...coDefinition({code_family})}]))));"],cwd=ROOT,text=True))

def execute(code,ram,reg,pc,stop):
    for _ in range(600):
        if pc==stop:return
        status,pc=reference(code[pc],ram,reg)
        assert status==0
    raise AssertionError(('execution limit',hex(pc)))

def trim(raw,g):
    d=raw-128
    return 128+(1 if d>=0 else -1)*((abs(d)*g+128)//256)

def main():
    codes={f:load_code(f) for f in recipes};reports=[];seen=set()
    for image in json.loads((ROOT/'analysis/firmware/catalog.json').read_text())['images']:
        family=image['code_family'];f=recipes[family];code=codes[family];early=family=='early'
        data=(ROOT/image['file']).read_bytes();rom=bytes(image['base_address'])+data
        path=ROOT/('analysis/disassembly.tsv' if early else 'analysis/firmware/families/late/disassembly.tsv')
        for r in csv.DictReader(path.open(encoding='utf-8'),delimiter='\t'):
            a=int(r['address'],16);b=bytes.fromhex(r['bytes']);assert rom[a:a+len(b)]==b
        for a,v in f['guards']:assert rom[a]==v,(image['id'],hex(a))
        for p in f['bytes']:assert rom[p['address']]==p['off']
        raw_values=range(255) if family not in seen else [0,108,128,148,254]
        seen.add(family);cases=0
        for override in [False,True]:
            for speed in [0,5120,11264,11392,11520,11648,11776,12288,30000,65535]:
                q=min(7168,max(0,speed-5120))//2;i,frac=divmod(q,256)
                cells=[p['on' if override else 'off'] for p in f['bytes']]
                gain=cells[i] if frac==0 else (cells[i]*(256-frac)+cells[i+1]*frac)//256
                for raw in raw_values:
                    ram=bytearray(rom);ram[:0x1800]=bytes(0x1800);reg=bytearray(64);put(reg,42,0x1700)
                    for p in f['bytes']:ram[p['address']]=p['on' if override else 'off']
                    put(ram,f['speed'],speed);ram[f['setting']]=raw
                    execute(code,ram,reg,f['entry'],f['stop'])
                    t=trim(raw,gain)
                    assert ram[f['gain']]==gain and ram[f['trim']]==t
                    qa,qb,ga,gb=(0xCE4,0xCE8,0x960,0x964) if early else (0xCFE,0xD00,0x968,0x96A)
                    put(ram,qa,2000);put(ram,qb,4000);put(ram,ga,300);put(ram,gb,220)
                    execute(code,ram,reg,0x8323 if early else 0x7885,0x83A3 if early else 0x7905)
                    assert rd(ram,0x942 if early else 0x95C,2)==(2000+4*(t-128))*300//256
                    assert rd(ram,0x944 if early else 0x95E,2)==(4000+4*(t-128))*220//256
                    if override:assert gain==255
                    elif speed>=11776:assert gain==0
                    cases+=1
        reports.append({'id':image['id'],'family':family,'cases':cases})
    print(json.dumps({'result':'passed','scope':'Actual CO lookup, rounding and both fuel lanes; stock/override, synthetic RAM; no hardware claim','total_cases':sum(r['cases'] for r in reports),'images':reports},indent=2))

if __name__=='__main__':main()
