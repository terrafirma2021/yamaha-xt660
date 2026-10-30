"""Per-BIN pin evidence. Never infer a connector from calibration equality.

The late pin assignments below were reviewed against its own ADC dispatch,
diagnostic selector copy, GPIO writes and timer/SCI registers. The diagrams are
manual references, not measured PCB continuity or physical ECU identification.
"""
import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/firmware/pin_audit.json'
LATE_MANUAL = 'https://www.motomatrix.co.uk/yamaha-pdf/XT660X-R2007_Suppl_manual.pdf'


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def listing(path):
    with (ROOT / path).open(encoding='utf-8') as f:
        return {int(r['address'], 16): r for r in csv.DictReader(f, delimiter='\t')}


def anchors(rows, addresses):
    return [dict(address=f'0x{a:04X}', bytes=rows[a]['bytes'], instruction=rows[a]['instruction']) for a in addresses]


def late_pins(primary, rows):
    pins = copy.deepcopy(primary)
    for p in pins:
        p.update(evidence=[], evidence_instructions=[], ram=[], diagnostic=None,
                 xt_wire=None, ecu_connector_positions=[], code_review=[])
        if p['category'] not in ('power',) and p['status'] != 'Datasheet':
            p.update(category='unresolved', status='Unassigned', role='Application role not established',
                     function='No function assignment is inherited from the early application.', register=None)

    def put(n, role, register, addresses, ram=(), diagnostic=None, category=None, note=None, status='Decoded'):
        p = pins[n-1]
        p.update(role=role, register=register, status=status,
                 category=category or primary[n-1]['category'],
                 function=note or 'Register use is checked in this application. External driver/conditioning and physical continuity are separate claims.',
                 evidence_instructions=anchors(rows, addresses), evidence=[f'0x{a:04X}' for a in addresses],
                 ram=[f'0x{a:04X}' for a in ram], diagnostic=diagnostic,
                 code_review=anchors(rows, addresses))

    put(1, 'Vehicle-speed pulses', 'PTIT 0x00E1 bit 2; TC2 0x0054', [0xF16D, 0x4850, 0x4852], [0xB06], 7)
    put(2, 'Ignition-coil driver command', 'TC3 0x0056; TCTL2 channel 3', [0xA35D, 0xA362, 0xA364, 0xA366, 0x4850, 0x4852], diagnostic=30)
    put(4, 'Ignition monitoring capture', 'TFLG1 0x004E bit 5', [0xD751, 0xD753, 0x4850, 0x4852], status='Candidate')
    put(5, 'Fuel-injector command', 'TC6 0x005C; PTIT bit 6', [0xA3E1, 0xBF02, 0xBF04, 0xBF64, 0x4850, 0x4852], diagnostic=36)
    put(6, 'Auxiliary PT7 output', 'PTT 0x00E0 bit 7; TCTL1 channel-7 mode 00', [0x6CC9, 0x6CD2, 0xA4C5, 0xA4E7, 0x4834, 0x4836, 0x4854, 0x4856], diagnostic=49,
        note='The late code writes GPIO bit 7 and diagnostic 49 calls this path. No direct TC7 compare write was found in the decoded late application. The early second-injector identity is not transferred; the external device remains unresolved.')
    put(12, 'PAIR / air-induction solenoid command', 'PTP 0x00F0 bit 0', [0x91EF, 0xA465, 0xA487, 0x482C, 0x482E], diagnostic=48, category='actuator',
        note='Normal control and diagnostic 48 assert PP0. This differs from early PP1. The 2007 manual identifies the Br/R air-induction circuit; the board route remains unmeasured.')
    put(13, 'Diagnostic / fault-pattern output', 'PTP 0x00F0 bit 1', [0xA077, 0xA080, 0xA635, 0xA653, 0x482C, 0x482E, 0x4878, 0x487B, 0x487D], diagnostic=54, category='internal',
        note='The output is used by fault-pattern logic and diagnostic 54. It is not the late PAIR command. Its external or internal destination is not established.')
    put(14, 'Radiator-fan relay command', 'PTP 0x00F0 bit 2', [0x6A55, 0x6A5A, 0xA57D, 0xA59F, 0x482C, 0x482E], diagnostic=51)
    put(15, 'Storage transaction select/strobe', 'PTP 0x00F0 bit 3', [0x4F8A, 0x4FB9, 0x482C, 0x482E])
    put(16, 'Headlight-relay command', 'PTP 0x00F0 bit 4', [0x9248, 0x924D, 0xA5D9, 0xA5FB, 0x482C, 0x482E], diagnostic=52)
    put(18, 'Additional output; destination unresolved', 'PTP 0x00F0 bit 6', [0xA23B, 0xA240, 0x482C, 0x482E], category='internal')
    put(19, 'Memory-test status/enable output', 'PTP 0x00F0 bit 7', [0x971D, 0x976F, 0x482C, 0x482E])
    put(20, 'Sidestand / start-interlock input', 'PORTB bit 0 -> 0x0898 -> 0x088F bit 6', [0x7EAF, 0x7EC1, 0x7ED9, 0x7EE6, 0x5D48, 0x4824, 0x4826], [0x898, 0x88F], 20)
    put(21, 'Starter-request input', 'PORTB bit 1 -> filtered 0x0898', [0x7EAF, 0x7EC1, 0xC263, 0xC27A, 0x4824, 0x4826], [0x898, 0x880], status='Candidate')
    put(24, 'Neutral input', 'PORTB bit 4 -> 0x0898 -> 0x088F bit 7', [0x7EAF, 0x7EC1, 0x7F0C, 0x7F19, 0x5D5E, 0x4824, 0x4826], [0x898, 0x88F], 21)
    for n in (26, 27):
        put(n, 'Port-B paired output; purpose unresolved', f'PORTB bit {n-20}', [0xAF8D, 0xAF8F, 0xAF91, 0xAFB1, 0xAFB3, 0xAFB5, 0xAFCE, 0x4824, 0x4826], category='internal',
            note='Bits 6/7 are emitted through a shared PORTB write. Their observed software use does not establish an external accessory or UART route.')
    for n in (39, 40):
        put(n, 'Bank-select GPIO initialized low', f'PORTE bit {n-37}', [0x4840, 0x4842, 0x48A0, 0x48A2, 0x48A4, 0x4B0E, 0x4B10, 0x4B12],
            note='The late application clears PE2/PE3. Its secondary dispatch tables point to an RTS stub. The early four-state analog-bank cycling is not inherited.')
    put(45, 'Injector-path readback / control bit', 'PORTA bit 0', [0xBF11, 0xBF13, 0x481C, 0x481E], category='internal',
        note='Read by injector scheduling, but DDRA configures it as output. External feedback wiring is not established.')
    put(47, 'Fuel-injection system relay command', 'PORTA bit 2', [0xA01B, 0xA028, 0xA525, 0xA543, 0x481C, 0x481E], diagnostic=50)
    put(49, 'Periodic service/watchdog candidate', 'PORTA bit 4', [0x56BD, 0x56C2, 0x481C, 0x481E], status='Candidate')
    adc = [0x61F5, 0x6304, 0x6353, 0x6877, 0x64BA, 0x6B1C, 0x6931, 0x6B29]
    sensor = [
        ('Throttle position (TPS)', [0x61FB, 0x5CE4], [0xBD2, 0xB0D], 1),
        ('Intake manifold pressure (MAP)', [0x6321, 0x5CF0], [0xCC4, 0xB0E], 3),
        ('Oxygen-feedback input', [0x6410, 0x648B, 0x6498], [0x8E2, 0x99F], None),
        ('Intake air temperature (IAT)', [0x690A, 0x5CFC], [0xB0F], 5),
        ('Fuel-system supply monitor', [0x64CC, 0x5D3C], [0xBF0, 0xB10], 9),
        ('Lean-angle / tip-over sensor', [0x6B1C, 0x5D28, 0x9BAF], [0x8E3], 8),
        ('Coolant temperature (ECT)', [0x69D0, 0x5D08], [0xB0C, 0x8DC], 6),
        ('Additional analog input; destination unresolved', [0x6B29], [0x8E4], None),
    ]
    for ch, (role, extra, ram, diagnostic) in enumerate(sensor):
        put(59+ch, role, f'ATD channel {ch}; selector 0x0085; dispatch 0x61B6',
            [0x6136, 0x6139, 0x613B, 0x6142, 0x6147, 0x6199, adc[ch], *extra], ram, diagnostic, category='sensor',
            note='Channel selection and the handler are checked in the late BIN. Channel 7 is sampled in the normal late sequence, unlike the early sequence.' if ch==7 else None)
    put(69, 'Dashboard/immobilizer serial RX', 'SCI1 data 0x00D7', [0x4863, 0x4866, 0x4868, 0x486A, 0xC433], category='communication')
    put(70, 'Dashboard/immobilizer serial TX', 'SCI1 data 0x00D7', [0x4863, 0x4866, 0xC35E], category='communication')
    for n, role, port in [(71, 'SPI data input', 0x4FA0), (72, 'SPI data output', 0x4F98), (73, 'SPI clock', 0x4872)]:
        put(n, role, 'SPI registers 0x00D8–0x00DD', [0x486C, 0x486E, 0x4870, port], category='communication')
    put(80, 'Crank-position sensor (CPS)', 'TC1 0x0052; capture channel 1', [0xD254, 0xD25C, 0x4850, 0x4852], category='sensor')
    return pins


def late_connector(early):
    c = copy.deepcopy(early)
    c.update(source_title='Yamaha XT660R/X 2007 supplement', source_url=LATE_MANUAL,
             source_pdf_pages=[55, 56, 81], target_scope='2007 R/X 34-position manual reference. Exact ECU/market fitment remains separate from the BIN code match.',
             coordinate_policy='U01–U17 / L01–L17: research coordinates counted left to right in the Yamaha drawing, not OEM cavity numbers.')
    by_wire = {s['wire']: s for s in early['slots'] if s['wire']}
    by_wire['P'] = dict(wire='P', role='Oxygen-sensor heater control', mcu_package_pins=[], association='Manual circuit only',
                        path='The 2007 drawing connects P to the oxygen-sensor heater, supplied separately by R/W. The MCU command pin has not been isolated; no GPIO is assigned by elimination.')
    by_wire['Gy/G'] = dict(wire='Gy/G', role='Oxygen-sensor signal', mcu_package_pins=[61], association='Function corroborated',
                           path='The 2007 drawing connects Gy/G to the oxygen signal, with Gy return. Late ADC channel 2 feeds the O2 fault-24 and feedback logic. The conditioning circuit remains untraced.')
    c['slots'] = []
    for row, wires in [('Upper', 'X X P L/W X Y/L Y/G Gy/G W Gy B/W X L Br/R R R/B O'),
                       ('Lower', 'X X B/Y R/L X L/B G/R Br/W P/W Y B/L L/R G/Y Y/B X X B')]:
        for col, wire in enumerate(wires.split(), 1):
            s = copy.deepcopy(by_wire.get(wire, dict(wire=None, role='Cross-marked position', mcu_package_pins=[], association='No connection shown', path='Cross-marked in the manual; physical contact population is not established.')))
            s.update(position=f'{row[0]}{col:02}', row=row, column=col, source_pdf_pages=[81], oem_cavity_number=None, continuity_verified=False)
            if wire=='Br/R':
                s['mcu_package_pins']=[12]
                s['path']='The 2007 Br/R air-induction circuit correlates with late diagnostic 48 and PTP bit 0 (PP0), not the early PP1 assignment. Board continuity is unmeasured.'
            elif wire not in ('P', 'Gy/G', 'X'):
                s['path']=f'2007 manual circuit: {s["role"]}. '+('PB0/PB4 remain alternatives through the interlock network; no unique physical assignment is proved.' if wire in ('B/Y','L/B') else 'The linked late MCU function is checked independently; no early instruction address or measured board route is implied.')
            c['slots'].append(s)
    return c


def make_report():
    primary=read('analysis/semantics/mcu_pin_overview.json')
    package=read('analysis/semantics/package_datasheet_review.json')
    review=read('analysis/semantics/code_pin_review.json')
    early=copy.deepcopy(primary['pins'])
    reviewed={p['pin']:p for p in review['pins']}
    for p in early:
        p['code_review']=copy.deepcopy(reviewed.get(p['pin'], {}).get('instructions', []))
        for a in p['code_review']:a['address']='0x'+a['address'].upper()
    early[60].update(role='Oxygen-feedback input (inactive in stock calibration)', status='Decoded',
        function='ADC2 feeds the oxygen-feedback and fault-24 paths. All five registered early BINs select variant 9 and zero eligibility grids, so stock feedback is inactive. This does not establish an early harness O2 terminal.')
    late_rows=listing('analysis/firmware/families/late/disassembly.tsv')
    families={'early':dict(pins=early, connector=copy.deepcopy(primary['ecu_connector'])),
              'late':dict(pins=late_pins(primary['pins'], late_rows), connector=late_connector(primary['ecu_connector']))}
    boot_rows=listing('analysis/firmware/xt660-2004-2006-companion/boot/disassembly.tsv')
    boot_rx=[a for a,r in boot_rows.items() if '0x00cf' in r['instruction'].lower() and r['instruction'].startswith(('LDA','LDB','LDAB'))]
    boot_tx=[a for a,r in boot_rows.items() if '0x00cf' in r['instruction'].lower() and r['instruction'].startswith(('STA','STB'))]
    assert boot_rx and boot_tx, 'Boot UART anchors missing'
    for family, f in families.items():
        for n, direction, direct in [(67,'RX',boot_rx[0]),(68,'TX',boot_tx[0])]:
            f['pins'][n-1].update(category='communication', status='Decoded', role='Boot / flashing serial '+direction,
                function='SCI0 handles the recovered boot protocol. A populated boot is required to verify these instructions in the selected BIN. The external connector-to-SCI0 route is not established by the manual or the flashing sketch.',
                register='SCI0 data 0x00CF; baud divisor 0x00C8–0x00C9', ram=[], diagnostic=None,
                boot_required=True, evidence_instructions=anchors(boot_rows,[0xF86E,0xF871,direct]), code_review=anchors(boot_rows,[0xF86E,0xF871,direct]))
        for p in f['pins']:
            combined={int(a['address'],16):a for a in p['evidence_instructions']+p['code_review']}
            p['evidence_instructions']=[combined[a] for a in sorted(combined)]
            p['evidence']=[a['address'] for a in p['evidence_instructions']]
            p['datasheet_pages']=reviewed.get(p['pin'],{}).get('register_pdf_pages', [98] if p['pin'] in (67,68) else [60])
            if p['pin'] in (67,68):p['datasheet_pages']=[73,98]
            if family=='late' and p['pin'] in (6,18,26):p['datasheet_pages']={6:[90,100],18:[101],26:[86]}[p['pin']]
            p['ecu_connector_positions']=[{k:s[k] for k in ('position','row','column','wire','association')} for s in f['connector']['slots'] if p['pin'] in s['mcu_package_pins']]
            p['package_checked']=package['reviewed_signals'][str(p['pin'])]==p['signal']
            assert p['package_checked']
    # Independent operand checks protect against silently swapping PAIR pins or
    # relabelling SCI1 data as the boot UART when regenerating the catalogue.
    for a, instruction in {0xA465:'BSET 0x00f0,0x1',0xA635:'BSET 0x00f0,0x2',0xA4C5:'BCLR 0x00e0,0x80',0x6139:'LDAB 0x0085',0x7ED9:'BRSET 0x898,0x1,0x7ef6',0x7F0C:'BRSET 0x898,0x10,0x7f29',0xC433:'LDAB 0x00d7'}.items():
        assert late_rows[a]['instruction']==instruction
    registry=read('analysis/firmware/catalog.json')
    images=[]
    for image in registry['images']:
        raw=(ROOT/image['file']).read_bytes();base=image['base_address'];rom=b'\xff'*base+raw
        assert hashlib.sha256(raw).hexdigest()==image['sha256']
        f=families[image['code_family']];checks=[]
        for p in f['pins']:
            evidence=p['evidence_instructions']+p['code_review']
            present=not p.get('boot_required') or image['boot_status']=='populated'
            if present:
                for a in evidence:
                    pc=int(a['address'],16);code=bytes.fromhex(a['bytes'])
                    assert rom[pc:pc+len(code)]==code,(image['id'],p['pin'],a)
            checks.append(dict(pin=p['pin'],code_verified=bool(evidence) and present,
                               code_status='Verified instruction bytes' if evidence and present else 'Boot not captured' if not present else 'No application assignment',
                               package_reference_checked=p['package_checked'],physical_package_verified=False,board_continuity_verified=False))
        table=0x6968 if image['code_family']=='early' else 0x61B6
        expected=[0x6996,0x6AA5,0x6AF6,0x6FC2,0x6C5E,0x71EB,0x70A3,0x707C] if image['code_family']=='early' else [0x61F5,0x6304,0x6353,0x6877,0x64BA,0x6B1C,0x6931,0x6B29]
        assert rom[table:table+16]==b''.join(a.to_bytes(2,'big') for a in expected)
        if image['code_family']=='late':
            assert rom[0x1841]==0x80, 'Re-review GPIO/PWM applicability for this variant'
            assert rom[0x4854:0x4858]==bytes.fromhex('c6305b48'), 'Re-review channel-7 output mux'
            assert list(rom[0x46C2:0x46C2+rom[0x46C1]])==[1,3,5,6,7,8,9,20,21,30,36,48,49,50,51,52,54,60,61,62,63,70]
        images.append(dict(id=image['id'],label=image['label'],variant=image['variant'],sha256=image['sha256'],family=image['code_family'],boot_status=image['boot_status'],checks=checks,
                           verified_code_pins=sum(c['code_verified'] for c in checks),connector_fitment='Manual reference; exact ECU hardware not independently confirmed'))
    flash=dict(source='dataset/sources/xt 660 r/XT660_PinOut.JPG',label='2C1-8591A-10 / XT660 2012',positions=34,
               source_sha256=hashlib.sha256((ROOT/'dataset/sources/xt 660 r/XT660_PinOut.JPG').read_bytes()).hexdigest(),
               source_numbering='Sketch numbering only; view side is not stated.',
               correlations=[dict(sketch_pin=3,wire='R',manual_position='U15',role='+12 V'),dict(sketch_pin=7,wire='B/W',manual_position='U11',role='Ground'),dict(sketch_pin=12,wire='Y/L',manual_position='U06',role='Communication')],
               finding='All three coloured terminals agree with the 34-position 2007 manual only under horizontal reflection. This is a consistent orientation hypothesis, not OEM numbering or an approved bench-wiring procedure.',
               early_finding='The 34-position sketch does not match the early 26-position drawing. Do not transfer its 3 / 7 / 12 numbers to the early ECU.',
               route_status='SCI0 is verified in the five populated boots; SCI1 is verified in all applications. The sketch labels K-line but does not establish which transceiver route reaches SCI0, SCI1, or both.')
    return dict(schema_version=1,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),package=package,
                families=families,images=images,flash_comparison=flash,
                sources=primary['sources']+[dict(id='xt-2007',title='Yamaha XT660R/X 2007 supplement',url=LATE_MANUAL,pdf_pages=[55,56,81])])


def build(check=False):
    report=make_report();content=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if check:assert OUT.read_text(encoding='utf-8')==content,'Pin audit is stale'
    else:OUT.write_text(content,encoding='utf-8',newline='\n')
    print('Pin audit: '+', '.join(i['id']+': '+str(i['verified_code_pins'])+' code-checked pins' for i in report['images']))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');build(p.parse_args().check)
