"""Reviewed additional pin configuration and consumers in both application families.

Configuration evidence establishes register bits, not a physical board destination.
The separate Configured status keeps startup-only findings out of function claims.
"""

LAYOUT = {
    'early': dict(pa=[0x5018, 0x501A, 0x501C, 0x501E],
                  pb=[0x5020, 0x5023, 0x5025, 0x5027, 0x5029, 0x502B, 0x502D, 0x502F, 0x5031],
                  pp=[0x5033, 0x5035, 0x5037, 0x5039],
                  pt=[0x503B, 0x503D, 0x503F, 0x5041, 0x505B, 0x505D, 0x505F, 0x5061, 0x5063, 0x5065],
                  ps=[0x5043, 0x5045, 0x5047, 0x5049, 0x5077, 0x5079],
                  pe=[0x504B, 0x504D], pk=[0x504F, 0x5051],
                  test=[0xA2B9, 0xA2BB, 0xA2BD, 0xA2BF, 0xA2C1, 0xA2C3, 0xA2C5, 0xA2C7,
                        0xA2CB, 0xA2CE, 0xA2D0, 0xA2D2, 0xA2D4, 0xA2D6, 0xA2D8, 0xA2DA,
                        0xA2DE, 0xA2E1, 0xA2F7, 0xA2F9, 0xA30C, 0xA505, 0xA50A, 0xA50D,
                        0xA510, 0xA51E, 0xA52B, 0xA52D, 0xA54B, 0xA54D, 0xA54F]),
    'late': dict(pa=[0x4818, 0x481A, 0x481C, 0x481E],
                 pb=[0x4820, 0x4822, 0x4824, 0x4826],
                 pp=[0x4828, 0x482A, 0x482C, 0x482E],
                 pt=[0x4830, 0x4832, 0x4834, 0x4836, 0x4850, 0x4852, 0x4854, 0x4856, 0x4858, 0x485A],
                 ps=[0x4838, 0x483A, 0x483C, 0x483E, 0x486C, 0x486E],
                 pe=[0x4840, 0x4842], pk=[0x4844, 0x4846],
                 test=[0x951A, 0x951C, 0x951E, 0x9520, 0x9522, 0x9524, 0x9526, 0x9528,
                       0x952C, 0x952F, 0x9531, 0x9533, 0x9535, 0x9537, 0x9539, 0x953B,
                       0x953F, 0x9542, 0x9558, 0x955A, 0x956D, 0x9799, 0x979E, 0x97A1,
                       0x97A4, 0x97B2, 0x97BF, 0x97C1, 0x97DF, 0x97E1, 0x97E3]),
}


def apply_configuration(pins, rows, family):
    layout = LAYOUT[family]

    def put(number, role, register, groups, note, pages, runtime=False, extra=()):
        p = pins[number - 1]
        addresses = sorted({a for group in groups for a in layout[group]} | set(extra))
        evidence = [dict(address=f'0x{a:04X}', bytes=rows[a]['bytes'], instruction=rows[a]['instruction']) for a in addresses]
        p.update(role=role, register=register, function=note, category='internal',
                 status='Decoded' if runtime else 'Configured', evidence=[r['address'] for r in evidence],
                 evidence_instructions=evidence, code_review=[], datasheet_pages=pages,
                 evidence_kind='runtime' if runtime else 'configuration')

    for n, bit in [(3, 4), (79, 0)]:
        put(n, f'GPIO output initialized {"high" if bit else "low"}',
            f'DDRT 0x00E2 bit {bit}; PTT 0x00E0; TIOS / TCTL1 / TCTL2', ['pt'],
            f'DDRT=0xD9 sets PT{bit} as output. '+
            ('TIOS bit 4 is set, but OM4:OL4=00 disconnects the compare action; the latch starts high. '
             if bit else 'TIOS bit 0 is clear and the output latch starts low. ')+
            'No dedicated pin-bit consumer or TC'+str(bit)+' access was found in the decoded application. '
            'This is a configured output, not an established spare input or an identified harness circuit.', [90, 100, 257, 385])
    for n, bit in [(17, 5)] + ([(18, 6)] if family == 'early' else []):
        put(n, 'GPIO output initialized high', f'DDRP 0x00F2 bit {bit}; PTP 0x00F0', ['pp'],
            f'DDRP=0xFF enables output and the startup latch sets PP{bit} high. No dedicated runtime write to this bit '
            'was found in the decoded application. The PWM alias does not establish PWM operation or identify the attached device.', [101, 264, 265])
    for n, bit in [(22, 2), (23, 3)] + ([(25, 5), (26, 6)] if family == 'early' else []):
        high = family == 'early' or bit in (2, 3)
        put(n, 'GPIO output initialized '+('high' if high else 'low'),
            f'DDRB 0x0003 bit {bit}; PORTB 0x0001', ['pb'],
            f'DDRB=0xEC configures PB{bit} as an output. Its startup latch is '+('high' if high else 'low')+
            '. Whole-port reads also enter the debounce snapshot; that does not make this bit a switch input. '
            'No dedicated runtime consumer of this bit was established in this family.', [74, 75, 86, 149, 150])
    for n, bit in [(48, 3)] + ([(46, 1)] if family == 'late' else []):
        put(n, 'GPIO output initialized '+('high' if bit == 3 else 'low'),
            f'DDRA 0x0002 bit {bit}; PORTA 0x0000', ['pa'],
            f'DDRA=0x1F makes PA{bit} an output, with startup latch '+('high' if bit == 3 else 'low')+
            '. Whole-port snapshots are present, but no dedicated runtime role for this bit was found. '
            +('The early PA1 second-injector readback is not present in this later application.' if bit == 1 else 'The board destination remains unknown.'),
            [74, 86, 147, 148])
    for n, bit in [(52, 5), (53, 6), (54, 7)]:
        gate = '0x08B1' if family == 'early' else '0x08B3'
        put(n, 'Service-test selector input '+str(bit - 5), f'DDRA 0x0002; PORTA 0x0000 mask 0xE0', ['pa', 'test'],
            'PA5/PA6/PA7 are inputs (DDRA=0x1F) read together as PORTA & 0xE0. With '+gate+
            ' bit 0x80 set and a repeated matching read: 0x80 invokes the full-range checksum test; '
            '0x00 enters an interrupt-masked infinite loop; 0x40 enters a destructive RAM-pattern test '
            '(0x5555 / 0xAAAA over 0x0800–0x0FFE). Other patterns do not enter these tests. '
            'These are application service/test selections, not the MCU hardware mode pins. External straps or test-point routing are unconfirmed.',
            [74, 86, 147, 148], runtime=True)
    put(74, 'GPIO output initialized high; SPI SS not selected',
        'DDRS 0x00EA bit 7; PTS 0x00E8; SPICR1/2 0x00D8/0x00D9', ['ps'],
        'DDRS=0xEA and PTS=0xFF initialize PS7 as a high output. SPI runs as master (SPICR1=0x50/0x54); '
        'SPICR2 has no decoded write and its reset MODFEN=0 leaves SS outside SPI control. '
        'The storage transaction strobe is PP3 instead. No dedicated PS7 toggle was found. '
        'This conclusion assumes the documented reset state; a nonstandard boot handoff can change it.', [73, 99, 100, 261, 463, 464])
    put(36, 'Port-K output direction configured', 'DDRK 0x0033 bit 7; PORTK 0x0032', ['pk'],
        'DDRK=0x80 selects PK7 output when the GPIO function is available. No decoded PORTK read/write establishes '
        'an application purpose or output latch value. ROMONE is a reset-time alternate function; ECS depends on the MCU operating mode.',
        [75, 88, 129, 159, 160])
    for n, bit in [(41, 4), (42, 5), (43, 6), (44, 7)]:
        direction = 'output' if bit in (4, 7) else 'input'
        put(n, f'Port-E {direction} direction configured', f'DDRE 0x0009 bit {bit}; PEAR 0x000A', ['pe'],
            f'DDRE=0x9F requests PE{bit} as {direction}. No dedicated runtime consumer of this bit or decoded '
            'PEAR write was found. The effective pin function depends on the reset mode and PEAR: '
            +{4: 'NECLK selects GPIO versus E-clock.', 5: 'MODA is sampled at reset; PIPOE can select instruction-pipe output.',
              6: 'MODB is sampled at reset; PIPOE can select instruction-pipe output.',
              7: 'XCLKS is sampled at reset; NOACCE can select CPU no-access output.'}[bit]+
            ' GPIO direction alone does not establish a reusable external connection.', [75, 86, 152, 153, 154])
    if family == 'late':
        put(25, 'Conditionally gated auxiliary output', 'PORTB 0x0001 bit 5; DDRB 0x0003', ['pb'],
            'PB5 starts low and is actively set at 0xA956 or cleared at 0xA95B. Enable byte 0x37E8 must equal 0x80 '
            '(true in all four registered late BINs). The gate checks a coolant-derived elapsed counter against map 0x37EE, '
            'a speed-indexed threshold from map 0x381C, fault-state bits and raw signal bounds. '
            'A communication/fault override preserves the previous output; reset handling at 0xC6AD clears it. '
            'This is a real output path, but the attached device is not identified. The manual oxygen-heater circuit '
            'is a comparison lead, not a proved PB5-to-heater connection.', [74, 75, 86], runtime=True,
            extra=[0xA8BD, 0xA8C2, 0xA8C5, 0xA8C8, 0xA8CB, 0xA8CE, 0xA8D3, 0xA8D6, 0xA8DD,
                   0xA8E0, 0xA902, 0xA905, 0xA908, 0xA90B, 0xA910, 0xA915, 0xA918, 0xA91C,
                   0xA921, 0xA924, 0xA929, 0xA92C, 0xA931, 0xA936, 0xA939, 0xA93D, 0xA941,
                   0xA946, 0xA94B, 0xA94E, 0xA952, 0xA956, 0xA95B, 0xC6AD])
        pins[24]['ram'] = ['0x09B4', '0x09B6', '0x09B8', '0x0CB2', '0x0C62', '0x08DC']
    # Review the remaining special positions explicitly without turning shared
    # clock/reset setup into a claim of per-pin runtime use or board continuity.
    for n in (7, 8, 9):
        pins[n-1]['function'] = ('Package debug/programming function. No application GPIO role or external ECU '
                                 'terminal route is established. This is not one of the SCI UART pins.')
    pins[27]['function'] = ('RESET package input/output. Startup enables low-voltage reset through LVDCR=0xC0; '
                            'that does not reveal the external reset network or establish a repurposable GPIO.')
    for n in (29, 30, 32):
        pins[n-1]['function'] = ('Oscillator/PLL package function. The recovered boot configures the PLL at '
                                 '0xF807–0xF81A. That boot is present in five registered images; the other four '
                                 'do not capture it. The fitted crystal, PLL filter components and board route '
                                 'cannot be identified from those register writes.')
    pins[36]['function'] = ('PE0/XIRQ is an input-only package function. No dedicated application use or external '
                            'connector route has been established. Its pin function is not a UART mux option.')
    pins[77]['function'] = ('The MC9S12T64 datasheet, PDF page 73, requires TEST to be tied to ground in normal '
                            'applications. That hardware requirement is not a measurement of the supplied ECU board.')


def apply_boot_configuration(pins, rows):
    p = pins[37]
    evidence = [dict(address=f'0x{a:04X}', bytes=rows[a]['bytes'], instruction=rows[a]['instruction'])
                for a in (0xF827, 0xF828, 0xF841)]
    p.update(role='External IRQ disabled by recovered boot', category='internal', status='Configured',
             register='IRQCR 0x001E bit 6 (IRQEN)', boot_required=True, evidence_kind='configuration',
             evidence_instructions=evidence, code_review=[], datasheet_pages=[87, 175],
             function='The recovered boot clears IRQCR to zero at 0xF841, disconnecting PE1 from external IRQ logic. '
             'There is no decoded application write to re-enable IRQEN. This is confirmed in populated boot images only; '
             'it does not identify an external wire or prove PE1 is electrically unconnected.')
