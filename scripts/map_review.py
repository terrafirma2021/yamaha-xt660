"""Per-axis research status from the catalogue's traced inputs.

This is an evidence inventory, not an independent execution test. Keep physical
assumptions separate from raw coordinate identities and cell arithmetic.
"""
import re


DOMAINS = {
    'speed': ('Speed coordinate', 'Confirm the timer clock and CPS pattern per crank revolution before treating the axis as RPM.'),
    'coolant': ('Effective coolant temperature code', 'Confirm the coolant circuit/temperature transfer and resolve the XT manual fallback conflict before assigning Celsius.'),
    'iat': ('Intake temperature code', 'Confirm the IAT circuit/temperature transfer before assigning Celsius.'),
    'load': ('Processed load coordinate', 'Stock and configurable sampling, filtering and signed normalization are replay-checked in both firmware families. Confirm sensor/circuit transfer and absolute pressure reference before assigning kPa.'),
    'throttle': ('Relative throttle coordinate', 'Confirm sensor/mechanical count-to-angle transfer before assigning degrees or percent throttle; baseline learning and filtering are replay-checked.'),
    'pressure_estimate': ('Pressure-derived estimate', 'Five-sample eligibility, tracking, replacement and source selection are replay-checked in both families, including the early alternate estimator. Confirm analog transfer and absolute reference before assigning kPa.'),
    'supply': ('Supply-derived code', 'Confirm the voltage divider and ADC reference before assigning volts; filtering and fault replacement are replay-checked.'),
    'throttle_delta': ('Filtered TPS change over four serviced samples', 'Confirm TPS count-to-angle transfer for angular change. The decoded coordinate is a position difference, not a time-normalized rate.'),
    'normalization': ('Combined normalization code', None),
    'adc': ('ADC count', None),
}

# Original (early-family) map IDs only. These are immediate lookup/consumer
# conditions, not a claim that every scheduler/interrupt combination was run.
SELECTIONS = {
    'main_quantity_B': 'Throttle quantity lookup at 0x7E33/0x7E57; 0x0A16 bit 2 chooses destination 0x0956 or 0x0958. ROM 0x4E62 replaces the axis only when both 0x08AF fault groups 0x0C and 0x30 are nonzero. Final fuel-mode weighting is separate',
    'modulo24_surface': 'Evaluated at 0x7B8C before the startup/normal fuel branch. Result is clamped (11 to 10, >=23 to 22) then passed through the phase limiter and event dispatcher',
    'correction_surface_A': 'Evaluated at 0x864E–0x8690 for the secondary quantity. Variant 9 skips the normal secondary injector scheduling entry',
    'correction_surface_B': 'Evaluated at 0xA405–0xA447; consuming normalization state at 0x8DF9 requires ROM 0x3130 == 128. Stock 255 disables it and restores centered offset 128',
    'correction_surface_C': 'Evaluated at 0xB3C3 into 0x0972, multiplied by pressure factor 0x0971 and saturated into 0x0970 for the load fuel path',
    'correction_surface_D': 'Computed at 0xB886 into 0x0A88; selected as the alternate base when 0x0885 bit 0x20 is set',
    'curve_18b6': 'Startup flag 0x0881:10 skips this gate. Otherwise 0x09A1:10 bypasses the delay; without that bypass ROM 0x18B5 == 128 inhibits it. Counter 0x0CAF reaching the looked-up threshold sets 0x09A1:40; this block does not clear the latched bit',
    'curve_1996': 'Used by one-shot initialization at 0x715A–0x716C and the startup fuel branch at 0x7BBA (0x0881:10 set). The startup branch retains Q8 precision',
    'curve_32ef': 'Initializes post-start state 0x0994 when 0x0884:08 is clear; reset path at 0x7381 reloads it if ROM 0x32EE != 128. Each fuel update decays this state; the larger of 0x0994 and 0x0996 is used',
    'curve_3301': 'Initializes post-start state 0x0996 when 0x0884:08 is clear; reset path at 0x7381 reloads it if ROM 0x32EE != 128. Each fuel update decays this state; the larger of 0x0994 and 0x0996 is used',
    'curve_4234': 'Evaluated in the fuel update at 0x74B8 and the periodic 0xB166 task, using the high byte of filtered supply 0x08DA; rounded result times eight supplies compensation 0x095E',
    'curve_19c6': 'Startup fuel branch (0x0881:10) evaluates pressure multiplier from 0x08F2',
    'curve_19ba': 'Startup fuel branch (0x0881:10) uses 0x08CE; either TPS fault bit in 0x08AF:0C forces this lookup input to zero',
    'curve_19a8': 'Startup fuel branch (0x0881:10) evaluates speed multiplier from 0x0900',
    'curve_34b0': 'Evaluated at 0x800C before the fuel-mode dispatcher at 0x8031; supplies 0x09A0 for the centered correction gain',
    'curve_3494': 'Evaluated at 0x8F91 into threshold 0x0A05 after filtered relative TPS is capped to byte 0x08EC; qualification tests follow at 0x8FAA',
    'curve_353a': 'Pressure factor shared by the two transient pulse calculations beginning at 0x9217 and 0x9438',
    'curve_351d': 'IAT factor shared by the two transient pulse calculations beginning at 0x9217 and 0x9438; consumer adds 384 before scaling',
    'curve_34ee': 'Throttle factor shared by the two transient pulse calculations beginning at 0x9217 and 0x9438',
    'curve_36c4': 'Adaptive eligibility block 0xA564–0xA63A requires counter 0x09B5 >= looked-up delay 0x09B4 along with both nonzero grids and the other qualification/fault gates; see INPUT_COORDINATES.md',
    'curve_36a4': 'Transition-triggered decrement when the feedback state 0x09A2:01 changes; updates centered correction 0x097E at 0xA6D3',
    'curve_36b2': 'Transition-triggered increment when the feedback state 0x09A2:01 changes; updates centered correction 0x097E at 0xA704',
    'curve_3220': 'Periodic 0xB166 task publishes IAT factor 0x0979; normal and startup fuel consumers use different stage scaling',
    'curve_3345': 'Periodic 0xB166 task publishes positive-delta coolant gain 0x098F; selected by the sign of the qualified transient change',
    'curve_3357': 'Periodic 0xB166 task publishes negative-delta coolant gain 0x0990; selected by the sign of the qualified transient change',
    'curve_323c': 'Evaluated at 0xB381 into 0x0971, combined with correction_surface_C to form the load fuel-path gain 0x0970',
    'curve_32e0': 'Evaluated at 0xB3DB into 0x0978 for the throttle fuel path',
    'curve_4a33': 'Evaluated at 0xB895 into 0x0A89; consumer at 0x96BA compares it with capped filtered relative TPS 0x08EC, not a spark-angle value',
    'curve_3315': 'Periodic lookup at 0xB89E publishes coolant enrichment 0x097B for the normal fuel gain',
    'curve_3327': 'Periodic lookup at 0xB8AA publishes coolant enrichment 0x097C for the normal fuel gain',
    'curve_34fd': 'Periodic lookup at 0xB8B9 publishes coolant factor 0x0A0F for the joint transient pulse calculation',
    'curve_4bac': 'Evaluated at 0xB8D3 into lower bound 0x0D05 for the selected base ignition value; normal/alternate selection and later scheduling are separate',
    'step_grid_35b0': 'Both adaptive grids must be nonzero in 0xA564–0xA63A, together with delay, coolant, pressure hysteresis, post-start, transient, neutral and fault gates. Every supplied early BIN has zero cells',
    'step_grid_363c': 'Both adaptive grids must be nonzero in 0xA564–0xA63A, together with delay, coolant, pressure hysteresis, post-start, transient, neutral and fault gates. Every supplied early BIN has zero cells',
    'step_grid_4c44': 'Both PAIR grids must be nonzero for the normal counter gate at 0x9CAE–0x9D61. Variant, coolant, post-start, centered-state and neutral/ratio gates apply; diagnostic bypass and fallback command branches are separate',
    'step_grid_4d48': 'Both PAIR grids must be nonzero for the normal counter gate at 0x9CAE–0x9D61. Variant, coolant, post-start, centered-state and neutral/ratio gates apply; diagnostic bypass and fallback command branches are separate',
}

HISTORY_CURVES = {'curve_34d0', 'curve_34da', 'curve_34e4', 'curve_355d', 'curve_3567', 'curve_3571'}
TRANSIENT_PULSE = HISTORY_CURVES | {'curve_353a', 'curve_351d', 'curve_34ee', 'curve_34fd', 'curve_3494'}
LATE_LOAD_DELTA = {'table_33bf','table_33d6','table_33ed','table_3404','table_341b','table_3432'}
LATE_THROTTLE_DELTA = {'table_3333','table_334a','table_3361','table_3378','table_338f','table_33a6'}
LOAD_DELTA_INACTIVE = ('All supplied BINs store load-change deadband 255 (early 0x3344; later 0x330C). '
                       'The preceding magnitude is capped at 127, so the qualified delta is always neutral '
                       'and these six gain maps contribute zero. Editing their cells alone cannot activate this contribution.')


def resolved_findings(m, unit):
    """Scoped, linkable claims; not a blanket per-map verification badge."""
    rows = [dict(claim='Lookup inputs, destination and immediate selection: '+m['selection'],
                 evidence='MAP_SELECTORS.md', method='Instruction trace; replay coverage varies by block')]
    domains = {a['domain'] for a in unit['axis_interpretations']}
    for domain, claim in {
        'throttle': 'ADC fault replacement, learned closed reference, relative position, movement latch and fuel-axis filtering are replay-checked in all nine BINs. Mechanical angle is not inferred.',
        'throttle_delta': 'Input = clamp(128 + current filtered TPS count - historical count, 0, 255). Stored ring mask 7 spans four serviced samples. Subtracting 128 gives signed count change; clipping applies at the endpoints.',
        'supply': 'Effective ADC-high-byte supply code substitutes 154 on its fault bit. A signed Q8 tracking filter feeds injector compensation; startup copies the source directly. Dwell uses the effective byte before that filter.',
        'load': 'Sample selection, filtering, normalization and alternate estimator paths have byte-checked instruction replay in both families.',
        'pressure_estimate': 'Pressure-estimate eligibility, retained-target tracking, replacement and source selection have byte-checked instruction replay in both families.',
        'speed': 'Speed-history selection, saturation/stale cases and scheduler arithmetic are replay-checked in all nine BINs; clock and crank geometry remain conditional.',
    }.items():
        if domain in domains:
            evidence = 'PRESSURE_ESTIMATE.md' if domain in {'load','pressure_estimate'} else 'INPUT_COORDINATES.md'
            rows.append(dict(claim=claim, evidence=evidence, method='Byte-checked instruction replay'))
    key=m['id']
    if key.startswith('delta_098'):
        claim = LOAD_DELTA_INACTIVE if key.startswith('delta_0989') else 'The throttle delta uses high-byte differences, magnitude cap 127, deadband, stale-state and high-throttle gates. These branches are replay-checked in all nine BINs. This is not a degrees/second coordinate.'
        rows.append(dict(claim=claim, evidence='INPUT_COORDINATES.md', method='Byte-checked instruction replay'))
    if key in {'main_quantity_B','curve_18b6','curve_36c4','step_grid_35b0','step_grid_363c','step_grid_4c44','step_grid_4d48'}:
        rows.append(dict(claim='Immediate eligibility/fault branches and threshold boundaries are replay-checked against all five early-family BINs. Tests use synthetic state fixtures, including deliberately active grids.', evidence='INPUT_COORDINATES.md', method='Byte-checked instruction replay'))
    if unit['cell_conversion'] is None:
        rows.append(dict(claim='Exact joint integer pulse arithmetic is decoded: the response, coolant, pressure, IAT and throttle factors together produce timer ticks. A factor alone has no unique millisecond scale.', evidence='MAP_CONSUMERS.md', method='Consumer arithmetic differential tests'))
    else:
        rows.append(dict(claim='Cell interpretation: '+unit['cell_conversion']+'. Integer rounding and consumer context are retained; conditional physical references remain explicit.', evidence='MAP_CONSUMERS.md', method='Consumer derivation; see scoped test coverage'))
    return rows


def per_image_input_findings(m, family):
    """Only facts whose source/calibration tests include all family members."""
    rows=[];key=m['id']
    if (family=='early' and key.startswith('delta_0989_gain_')) or (family=='late' and key in LATE_LOAD_DELTA):
        rows.append(LOAD_DELTA_INACTIVE)
    if (family=='early' and key.startswith('delta_0985_gain_')) or (family=='late' and key in LATE_THROTTLE_DELTA):
        rows.append('Qualified throttle change is a centered high-byte difference with magnitude cap 127, deadband, stale-state and high-throttle gates. Input formation is replay-checked in this BIN; it is not a physical rate.')
    if family=='early' and key in HISTORY_CURVES:
        rows.append('Input is the clipped byte 128 + filtered TPS change over four serviced samples. Raw minus 128 gives relative TPS count change; it does not give degrees/second.')
    if family=='late' and key in {'table_34ae','table_34b6','table_34be','table_3640','table_3648','table_3650'}:
        rows.append('The later family retains history-change word 0x08F8, clipped to 0..1151, alongside byte 0x08FA capped at 255. This map uses an indexed axis stage; the early family raw-minus-128 map-axis conversion must not be copied onto its indices.')
    if (family=='early' and key=='curve_4234') or (family=='late' and key=='table_385a'):
        rows.append('Axis uses the high byte of the Q8 filtered supply word. Fault replacement is 154; startup copies the effective source directly. Filter and fault branches are replay-checked; volts still require the divider/reference.')
    if (family=='early' and key=='dwell_supply_speed') or (family=='late' and key=='table_413a'):
        rows.append('Supply axis uses the effective ADC-high-byte code before the injector-compensation filter. Its fault replacement is 154. Volts still require the divider/reference.')
    return rows


def input_review(m):
    axes = [(k, a) for k in ('row_axis', 'column_axis') if (a := m.get(k))]
    if m['kind'] == '1D_uniform_axis':
        axes = [('uniform_input', {'input': '; '.join(m['inputs'])})]
    result = []
    for name, axis in axes:
        # The manually traced input also records fault substitutions. A nearby
        # LDD literal in the automatic call window is not the normal source.
        index = 0 if name in ('row_axis', 'uniform_input') or len(m['inputs']) == 1 else 1
        source = m['inputs'][index]
        addresses = {int(x, 16) for x in re.findall(r'0x([0-9a-f]+)', source, re.I)}
        domain = None
        if 'ADC channel' in source:
            domain = 'adc'
        for candidates, key in [({0x900, 0x902, 0x8f8}, 'speed'), ({0x8f4}, 'coolant'),
                                ({0x8f5}, 'iat'), ({0xc90}, 'load'),
                                ({0x8e8, 0x8ce}, 'throttle'), ({0x8f2}, 'pressure_estimate'),
                                ({0x8d9, 0x8da}, 'supply'), ({0x8ed}, 'throttle_delta'),
                                ({0xcd0}, 'normalization')]:
            if addresses & candidates:
                assert domain is None, (m['id'], source)
                domain = key
        assert domain is not None, (m['id'], name, source)
        label, gap = DOMAINS[domain]
        result.append(dict(axis=name, source=source, domain=domain, meaning=label,
                           raw_coordinate_status='Traced in catalogue',
                           physical_status='Not required: internal code/count' if gap is None else 'Open',
                           open_requirement=gap))
    assert result, m['id']
    return result


def remaining_questions(m, unit):
    items = []
    profiles = set(unit.get('requires', []))
    for axis in unit['axis_conversions']:
        profiles.update(axis['requires'])
    if 'nominal_xt_timer' in profiles:
        items.append('Confirm actual timer clock; the 500 kHz profile remains service-correlated, not measured.')
    if 'nominal_xt_crank' in profiles:
        items.append('Confirm CPS pattern per mechanical revolution; the 12-pitch / 180-degree speed-period interpretation remains conditional.')
    for axis in unit['axis_interpretations']:
        gap = axis['open_requirement']
        if gap and axis['domain'] != 'speed' and gap not in items:
            items.append(gap)
    conversion = unit['cell_conversion']
    if conversion == 'temperature_celsius_candidate':
        items.append(DOMAINS['coolant' if m['id'].startswith('coolant') else 'iat'][1])
    if conversion == 'spark_relative_degrees':
        items.append('Establish CPS edge relative to mechanical TDC and the coil firing edge; relative scheduler degrees are not absolute BTDC.')
    if conversion == 'injection_event_code':
        items.append('Establish event-code phase relative to the physical crank cycle, including special scheduling modes.')
    if conversion == 'relative_tps_counts':
        items.append('Confirm the relative TPS count-to-mechanical-angle transfer for the cell threshold.')
    if m['id'] in {'curve_1854', 'curve_1880'}:
        items.append('Check concurrent interrupt/task behaviour around the replayed calculation blocks on the identified ECU; the documented calculation branches are already covered.')
    if m['id'] in TRANSIENT_PULSE:
        items.append('Replay the complete transient trigger, pulse accumulation and output scheduling sequence together; current tests cover input history, map selection and isolated pulse arithmetic.')
    if m['id'] in {'curve_32ef','curve_3301'}:
        items.append('Replay post-start initialization, reset/reload and decay as one lifecycle; current tests establish the individual lookups and maximum-selection arithmetic.')
    if m['id']=='modulo24_surface':
        items.append('Replay the phase limiter and every special injection dispatcher mode as one event sequence; modulo interpolation alone does not verify event timing.')
    if m['id']=='correction_surface_A':
        items.append('Validate the secondary-injector scheduling path under the non-XT variant configurations; the normal XT variant skips that entry.')
    if m['id'] in {'correction_surface_D','curve_4a33'}:
        items.append('Replay the early-family alternate ignition state transitions together with final coil scheduling; the later-family state tests cannot certify this early image.')
    items.append('Validate edited behaviour, permitted ranges and output effects on the identified ECU; software arithmetic checks do not provide bench sign-off.')
    return list(dict.fromkeys(items))
