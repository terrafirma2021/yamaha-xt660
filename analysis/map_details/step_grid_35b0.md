# Adaptive feedback enable vs speed and throttle

<!-- map-name -->
Stable ID: `step_grid_35b0`. Category: Feedback.

Logical eligibility gate: zero inhibits the path; nonzero permits further tests. It is not a physical percentage or a complete enable decision. Both stock adaptive-feedback grids contain only zero.

Naming evidence: [recovered derivation](../../analysis/semantics/EXTENDED_MAPS.md).
<!-- /map-name -->

Adaptive feedback eligibility grid; zero clears feedback-enable path

Cells: **0x35B0–3613**, 10 rows × 10 columns, 8-bit unsigned big-endian values.

Inputs: u16 RAM 0x0900: selected speed code; u16 RAM 0x08E8.

Output: u8 RAM 0x09AE; column/row bins at 0x09B0/0x09B1.

Selection: Both adaptive grids must be nonzero in 0xA564–0xA63A, together with delay, coolant, pressure hysteresis, post-start, transient, neutral and fault gates. Every supplied early BIN has zero cells.

Interpolation: none; strict > threshold selects upper bin; equality stays in lower bin.

**Tuning export is disabled.** Conditional conversions and unresolved physical references are recorded per map in the [engineering-unit companion](../semantics/physical_units.json); see the [derivation](../semantics/UNIT_DECODING.md).

## Row Axis

Source: 0x359C. u16 RAM 0x0900

lower bin; bin = number of thresholds strictly below input

`4096, 6144, 8192, 10496, 12288, 14336, 16384, 18432, 23040`

Following unused stored word: `{"address": "0x35AE", "raw": 24576, "status": "present but not compared by this lookup"}`.

## Column Axis

Source: 0x3588. u16 RAM 0x08E8

lower bin; bin = number of thresholds strictly below input

`0, 768, 1024, 1600, 2624, 3648, 5248, 9472, 15744`

Following unused stored word: `{"address": "0x359A", "raw": 52416, "status": "present but not compared by this lookup"}`.

## Raw cells

```
0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0
0 0 0 0 0 0 0 0 0 0
```

## Instruction evidence

Addresses refer to the unchanged image. Windows around entry/call sites provide context, not a complete execution trace.

```
abd2  b136ec  CMPA 0x36ec
abd5  2303  BLS 0xabda
abd7  b636ec  LDAA 0x36ec
abda  6a00  STAA 0,IX
abdc  3d  RTS
abdd  c60a  LDAB #0xa
abdf  53  DECB
abe0  53  DECB
abe1  58  ASLB
abe2  fd08e8  LDY 0x8e8
abe5  ce3588  LDX #0x3588
abe8  1ae5  ABX
abea  ad00  CPY 0,IX
abec  2207  BHI 0xabf5
abee  c002  SUBB #0x2
abf0  24f3  BCC 0xabe5
abf2  c7  CLRB
abf3  2003  BRA 0xabf8
```

[Machine-readable catalogue](../maps.json) · [All map breakdowns](../MAP_DETAILS.md)

<!-- generated-unit-decoding -->
## Recovered consumer and unit interpretation

logical behavior decoded.

Conversion: `raw != 0`; unit: **eligible**.

Zero inhibits this gate; any nonzero byte passes this gate. Other conditions can still inhibit the function.

Eligibility: zero inhibits the documented path; nonzero permits its next tests. Not a continuous physical quantity.

Stock activation: Every stock cell is zero, rejecting this normal feedback-eligibility gate.

row_axis conversion: `speed_rpm`; requires `nominal_xt_timer`, `nominal_xt_crank`.
Converted values: 800, 1200, 1600, 2050, 2400, 2800, 3200, 3600, 4500.

### Every input axis

| Axis | Traced source | Interpretation | Physical scale |
|---|---|---|---|
| row_axis | u16 RAM 0x0900: selected speed code | Speed coordinate | Confirm the timer clock and CPS pattern per crank revolution before treating the axis as RPM. |
| column_axis | u16 RAM 0x08E8 | Relative throttle coordinate | Confirm sensor/mechanical count-to-angle transfer before assigning degrees or percent throttle; baseline learning and filtering are replay-checked. |

### Resolved in the code

- Lookup inputs, destination and immediate selection: Both adaptive grids must be nonzero in 0xA564–0xA63A, together with delay, coolant, pressure hysteresis, post-start, transient, neutral and fault gates. Every supplied early BIN has zero cells [Instruction trace; replay coverage varies by block](../semantics/MAP_SELECTORS.md).
- ADC fault replacement, learned closed reference, relative position, movement latch and fuel-axis filtering are replay-checked in all nine BINs. Mechanical angle is not inferred. [Byte-checked instruction replay](../semantics/INPUT_COORDINATES.md).
- Speed-history selection, saturation/stale cases and scheduler arithmetic are replay-checked in all nine BINs; clock and crank geometry remain conditional. [Byte-checked instruction replay](../semantics/INPUT_COORDINATES.md).
- Immediate eligibility/fault branches and threshold boundaries are replay-checked against all five early-family BINs. Tests use synthetic state fixtures, including deliberately active grids. [Byte-checked instruction replay](../semantics/INPUT_COORDINATES.md).
- Cell interpretation: eligibility. Integer rounding and consumer context are retained; conditional physical references remain explicit. [Consumer derivation; see scoped test coverage](../semantics/MAP_CONSUMERS.md).

### What remains for this map

- Confirm actual timer clock; the 500 kHz profile remains service-correlated, not measured.
- Confirm CPS pattern per mechanical revolution; the 12-pitch / 180-degree speed-period interpretation remains conditional.
- Confirm sensor/mechanical count-to-angle transfer before assigning degrees or percent throttle; baseline learning and filtering are replay-checked.
- Validate edited behaviour, permitted ranges and output effects on the identified ECU; software arithmetic checks do not provide bench sign-off.

See [consumer derivations](../semantics/MAP_CONSUMERS.md), [per-map status](../semantics/MAP_RESOLUTION.md) and [machine-readable values](../semantics/physical_units.json). Complete axis interpretation, mode coverage and hardware validation are separate from this cell interpretation.
