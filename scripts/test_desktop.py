"""Exercise the compiled Windows app, including independent XML patch replay."""
import hashlib
import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'dist/yamaha-xt660-windows-v0.2.2'
EXE=PACKAGE/'XT660.FileTool.exe'


def run(*args, code=0):
    if args[0]=='--fix' and code==0 and Path(args[2]).exists():
        Path(args[2]).unlink() # Test-owned temporary output only.
    result=subprocess.run([str(EXE),*map(str,args)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==code,(args,result.returncode,result.stdout,result.stderr)
    return result.stdout


run('--verify-bundle')
records=json.loads((PACKAGE/'manifest.json').read_text())['definitions']
count=0
with tempfile.TemporaryDirectory(prefix='xt660-desktop-') as temp:
    temp=Path(temp); edited=temp/'edited.bin'; fixed=temp/'fixed.bin'
    for r in records:
        source=PACKAGE/r['bin_file'];data=source.read_bytes();base=r['base_address']
        info=json.loads(run('--inspect',source));assert info['matched'] and info['bytes']==len(data)
        run('--fix',source,fixed)
        corrected=fixed.read_bytes();assert len(corrected)==len(data)
        assert all(a==b or n+base in (0xF7FC,0xF7FD) for n,(a,b) in enumerate(zip(data,corrected)))
        assert sum(int.from_bytes(corrected[n:n+2],'big') for n in range(0x1800-base,0xF800-base,2))&65535==0xAA55
        assert json.loads(run('--inspect',fixed))['checksum_pass']
        run('--fix',source,source,code=1)
        xml=ET.parse(PACKAGE/r['file'])
        first=xml.find("XDFTABLE/XDFAXIS[@id='z']/EMBEDDEDDATA")
        offset=int(first.attrib['mmedaddress'],16);copy=bytearray(data);copy[offset]^=1;edited.write_bytes(copy)
        assert json.loads(run('--inspect',edited))['matched'];run('--fix',edited,fixed)
        assert fixed.read_bytes()[offset]==copy[offset]
        for patch in xml.findall('XDFPATCH'):
            original=bytearray(data);after=bytearray(data);changed=[]
            for e in patch.findall('XDFPATCHENTRY'):
                a=int(e.attrib['address'],16);n=int(e.attrib['datasize'],16)
                before=bytes.fromhex(e.attrib['basedata']);new=bytes.fromhex(e.attrib['patchdata'])
                assert n==len(before)==len(new) and 0<=a<a+n<=len(data)
                original[a:a+n]=before;after[a:a+n]=new
                changed.extend(a+i for i in range(n) if before[i]!=new[i])
            edited.write_bytes(after)
            assert json.loads(run('--inspect',edited))['matched'],(r['id'],patch.findtext('title'))
            run('--fix',edited,fixed)
            for a in changed:assert fixed.read_bytes()[a]==after[a]
            # An unrecognised byte in code must not be disguised by other valid patches.
            invalid=bytearray(after);invalid[0xF900-base]^=1;edited.write_bytes(invalid)
            assert not json.loads(run('--inspect',edited))['matched'];run('--fix',edited,fixed,code=1)
            for e in patch.findall('XDFPATCHENTRY'):
                a=int(e.attrib['address'],16);before=bytes.fromhex(e.attrib['basedata']);after[a:a+len(before)]=before
            assert after==original
            count+=1
        assert hashlib.sha256(source.read_bytes()).hexdigest()==r['bin_sha256']
    edited.write_bytes(b'bad');run('--inspect',edited,code=1)
    run('--compare',source,source)
    run('--compare',source,edited,code=2)
print(f'Desktop executable verified: 9 source BINs, map edits, {count} reversible XDF patches, unknown-code rejection, checksum saves and immutable sources.')
