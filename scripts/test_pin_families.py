"""Check per-BIN provenance, family differences and connector non-equivalence."""
import re
from unittest.mock import patch
import pin_families as audit

report=audit.make_report()
early=report['families']['early'];late=report['families']['late']
assert len(report['images'])==9
assert len({i['sha256'] for i in report['images']})==9
for family,expected in ((early,26),(late,34)):
    assert [p['pin'] for p in family['pins']]==list(range(1,81))
    slots=family['connector']['slots']
    assert len(slots)==expected and len({s['position'] for s in slots})==expected
    assert all(s['oem_cavity_number'] is None and not s['continuity_verified'] for s in slots)
    for p in family['pins']:
        assert p['package_checked']
        assert [s['position'] for s in p['ecu_connector_positions']]==[s['position'] for s in slots if p['pin'] in s['mcu_package_pins']]

def wire(f,w):return next(s for s in f['connector']['slots'] if s['wire']==w)
assert wire(early,'Br/R')['mcu_package_pins']==[13]
assert wire(late,'Br/R')['mcu_package_pins']==[12]
assert wire(late,'P')['mcu_package_pins']==[]
assert wire(late,'Gy/G')['mcu_package_pins']==[61]
assert sum(s['wire'] is None for s in late['connector']['slots'])==9
assert late['pins'][5]['diagnostic']==49 and 'Auxiliary' in late['pins'][5]['role']
assert late['pins'][12]['diagnostic']==54
assert late['pins'][65]['ram']==['0x08E4']
assert late['pins'][45]['status']=='Unassigned'
for f in (early,late):
    for w in ('B/Y','L/B'):
        assert wire(f,w)['association']=='Unresolved alternatives'
        assert wire(f,w)['mcu_package_pins']==[20,24]
    assert all(f['pins'][n-1]['boot_required'] for n in (67,68))
    assert all('SCI1' in f['pins'][n-1]['register'] for n in (69,70))

for image in report['images']:
    assert len(image['checks'])==80
    checks={p['pin']:p for p in image['checks']}
    assert checks[67]['code_verified']==(image['boot_status']=='populated')
    assert checks[68]['code_verified']==checks[67]['code_verified']
    assert all(checks[n]['code_verified'] for n in (1,2,5,20,24,59,60,61,62,63,64,65,69,70,80))
    assert all(not c['physical_package_verified'] and not c['board_continuity_verified'] for c in checks.values())
    assert image['verified_code_pins']==(38 if image['family']=='late' else 37 if image['boot_status']=='populated' else 35)

for r in report['flash_comparison']['correlations']:
    s=next(s for s in late['connector']['slots'] if s['position']==r['manual_position'])
    assert s['column']==18-r['sketch_pin'] and s['row']=='Upper' and s['wire']==r['wire']

# Byte anchors are not just decorative evidence: corrupt one expected late
# instruction without editing a BIN, and the generation must fail.
real=audit.anchors
def damaged(rows,addresses):
    result=real(rows,addresses)
    for r in result:
        if r['address']=='0xA465':r['bytes']='000000'
    return result
with patch.object(audit,'anchors',damaged):
    try:audit.make_report()
    except AssertionError:pass
    else:raise AssertionError('Corrupted PAIR byte evidence was accepted')

late_rows=audit.listing('analysis/firmware/families/late/disassembly.tsv')
assert not any(re.fullmatch(r'ST(?:AA|AB|D|X|Y) 0x0*5e',r['instruction']) for r in late_rows.values())
print('Verified all nine BINs, two independent pin families, 26/34-position references, boot coverage and rejection of corrupted byte evidence.')
