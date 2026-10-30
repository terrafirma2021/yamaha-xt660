"""Check static evidence against a locally supplied YamahaFlasher.exe; never execute it."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def verify(path):
    evidence = json.loads((ROOT/'analysis/firmware/yamaha_flasher_evidence.json').read_text(encoding='utf-8'))
    data = Path(path).read_bytes()
    if len(data) != evidence['source']['size'] or hashlib.sha256(data).hexdigest() != evidence['source']['sha256']:
        raise ValueError('Executable identity differs from the inspected build; do not reuse its addresses')
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    if data[pe:pe+4] != b'PE\0\0':
        raise ValueError('Invalid PE signature')
    sections, optional_size = struct.unpack_from('<H', data, pe+6)[0], struct.unpack_from('<H', data, pe+20)[0]
    image_base = struct.unpack_from('<I', data, pe+24+28)[0]
    section_table = pe+24+optional_size
    def read_va(va, count):
        rva = va-image_base
        for index in range(sections):
            virtual_size, start, raw_size, raw = struct.unpack_from('<IIII', data, section_table+index*40+8)
            if start <= rva and rva+count <= start+raw_size:
                offset = raw+rva-start
                return data[offset:offset+count]
        raise ValueError(f'Address outside file-backed PE sections: {va:X}')
    for anchor in evidence['anchors']:
        expected = bytes.fromhex(anchor['bytes'])
        if read_va(int(anchor['va'],16),len(expected)) != expected:
            raise ValueError('Anchor mismatch: '+anchor['claim'])
    record = evidence['session_record']
    boot = (ROOT/record['firmware_file']).read_bytes()
    if hashlib.sha256(boot).hexdigest() != record['firmware_sha256']:
        raise ValueError('Companion firmware identity differs')
    offset = int(record['exe_file_offset'],16)
    default = bytes.fromhex(data[offset:offset+32].decode('ascii'))
    if default != boot[0xFF10-0x1800:0xFF20-0x1800] or hashlib.sha256(default).hexdigest() != record['record_sha256']:
        raise ValueError('Session record differs from the boot')
    print(f"Verified {len(evidence['anchors'])} native/data anchors and exact 16-byte boot session-record match. No executable launched.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path)
    args = parser.parse_args()
    verify(args.exe)
