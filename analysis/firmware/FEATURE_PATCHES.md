# BIN feature controls

The [Tools page](../../tools/index.html) detects feature states from the loaded bytes. Each feature has **Enabled / Disabled** radio buttons. Unsupported controls and controls without an identified BIN are greyed out. Source files remain untouched. Changes, undo and reset use a draft with automatic startup-checksum compensation; exported reports include feature states and byte differences.

These recipes are instruction-tested against all nine registered BINs. **No patched ECU has been bench-tested.** An enabled PAIR control means the firmware may command the valve; it is not a live valve reading. Early applications without configured O2 feedback show that row disabled and read-only. Unexpected patch bytes remain unavailable.

## Supported recipes

All addresses below are CPU addresses. For a 59,392-byte BIN, subtract `0x1800` to obtain the file offset. The tool handles this automatically.

| Feature | Early application | Late application | Disabled state |
|---|---|---|---|
| Immobilizer | `4E7D` â†’ RAM `0DD5`, copy at `61DE` | `4619` â†’ RAM `0E4D`, copy at `58DF` | `00 â†’ 80` |
| PAIR valve command | `9D5A` and `BAC3`, PTP bit 1 | `91EF` and `A465`, PTP bit 0 | Replace opcode `4C` (BSET) with `4D` (BCLR), keeping operands |
| Overrun cut | `348A`: `90 â†’ FF` | `3451`: `7D â†’ FF` and `3456`: `85 â†’ FF` | Impossible entry condition plus restoration of the cut multiplier |

| O2 feedback and new O2 faults | Not configured in the registered early images; read-only | `368E`: `80 â†’ 00` | Bypass feedback eligibility and faults 24/31/32 |
| Sidestand ECU cut-off | `CC5E`: `1C â†’ 1D`; `4E6C`: `00 â†’ 80` | `C2C4`: `1C â†’ 1D`; `4608`: `00 â†’ 80` | Prevent the shared inhibit assertion and new fault 19 |
| Lean-angle cut-off | `4E91`: `00 â†’ 80` | `462D`: `00 â†’ 80` | Bypass tip-over detection and use the fault-41 clear path |

Enabling restores the recipe's original registered bytes. A partial patch or unexpected parameter is unverified, not guessed to be enabled. Imported files with only these recognised changes and checksum compensation can be matched byte-for-byte against registered references outside those positions. That is labelled a recognised feature-edited layout, not an exact source identity. Files with other edits remain inspection-only on re-import.

### Immobilizer

Early `A9AF` and late `9CF1` compare the copied configuration with `80` and bypass authentication when equal. Startup and serial paths also consume this configuration. Existing owner and immo-off images therefore display Disabled without trusting filenames. The late immo-off source also differs at `4751`; this additional byte is preserved, not used as the authentication-state detector. Re-enabling restores authentication code behaviour; it does not create or pair keys.

### PAIR valve

Both normal control and the diagnostic actuator command must be covered. Early `9D5A` / `BAC3` assert `F0:02`; late `91EF` / `A465` assert `F0:01`. These are different GPIO bits between families. Replacing both assertions with clears covers the direct assertion writers in the decoded application. Startup initialises these bits clear, and the existing off/failsafe paths clear them.

Zeroing the air-induction grids alone is insufficient: fault/mode override paths can still reach the assertion. This recipe changes the commands instead of those grids. Physical output voltage and valve operation still need hardware verification; firmware status bookkeeping may continue to report a requested on-state.

### Deceleration fuel cut: targeted control-flow bypass

Early `765D–77B1` and late `6E6B–6FC6` evaluate coolant, runtime age, speed hysteresis, throttle/load qualification, delays and neutral state. They set RAM `0886:40` and write zero to fuel multiplier `097A`. The normal injection dispatcher consumes that cut flag. This is separate from rev-limit cut logic.

The current recipe uses two three-byte CPU12 extended jumps per family:

| Purpose | Early | Late |
|---|---|---|
| Skip qualification and transition handling; enter existing cleanup | `765D: JMP 777A` | `6E6B: JMP 6F8F` |
| After cleanup, always restore `097A=80`, regardless of temperature/speed/neutral | `778D: JMP 77A2` | `6FA2: JMP 6FB7` |

Both jumps replace whole three-byte `LDAB` instructions. Cleanup clears the qualification counter, bits `10`, `08` and `40` of `0886`, and transition flags `088A`. The second jump is necessary: the original exit path can otherwise leave a zero or reduced multiplier in place. Together they prevent entry and recover from an already-active overrun cut. The remaining application continues at `77B1` / `6FC6`.

Only six instruction bytes change. Coolant/runtime thresholds and main fuel/ignition maps stay stock. The shared throttle-processing latch `088D:04` remains untouched: clearing it globally would also alter ignition-map indexing and another fuel path. Existing ignition trim `0A86` / `0A8E` is not forcibly reset; its normal recovery logic remains. The bypass prevents new overrun transition handling in the skipped block and clears the overrun flag used by downstream handling. It does not disable every ignition correction, other fuel-cut flag, or rev limiter.

Changing only `76D3` / `6EE8` from flag-set to flag-clear is insufficient: the following jump still zeroes fuel. The implemented bypass instead skips the whole qualification/transition section and explicitly restores the multiplier.

#### Earlier threshold-based exports

The previous recipe used early `348A:90→FF`, or late `3451:7D→FF` plus `3456:85→FF`. It remains recognised as a disabled **legacy threshold patch** only when the original instruction bytes are intact. The tool explains this on import. Clicking Disabled replaces that recipe with the targeted jumps and restores the original thresholds; clicking Enabled restores stock code and thresholds. Import itself does not silently migrate an existing file. Reports identify legacy status. Partial and mixed recipes remain unavailable.

## O2 feedback and diagnostic reporting

The late application has a verified master setting at `368E`. Disabling it bypasses feedback eligibility and the detection paths for faults 24, 31 and 32. This prevents new current/history flags and their log-update requests; it does **not** erase existing faults or hide them from the serial reply. The stock early BINs use variant 9, skip these fault paths and contain zero feedback eligibility grids, so no enable patch is offered for them.

The previous XDF candidate at `466E` remains excluded: it affects a serial-storage default and has not been established as the master O2 control. The new recipe uses the directly consumed `368E` flag instead.

See [O2 control, fuel maps and fault reporting](../semantics/O2_CONTROL.md) for the consumer addresses, neutral correction calculation, retained base fuel maps, stored-history limitation and manufacturer fault definitions.

## One overrun control

The page now shows one **Overrun cut** row. The shared deceleration flag affects injection and linked ignition corrections, but it is not itself a normal coil-charge inhibit. Selected-path execution with `0886:40` both clear and set proves that injection is gated while coil charging can still be scheduled. Separate rev-limit fuel/spark cut flags remain untouched. Combining the UI row does not equate fuel cut with suppressing every spark.

## Reproducible checks

[Sidestand and lean-angle controls](../semantics/INTERLOCK_CONTROLS.md) document the two interlock recipes, their source paths and physical limitations. The sidestand patch does not change the external starting relay. The lean-angle patch is not a blanket erase of existing trip latches or stored faults. No clutch switch is provided in the editor.

`python scripts/test_feature_patches.py` executes selected CPU12 paths using byte-checked disassembly for both families and all nine registered BINs. It includes a stock positive control that enters fuel cut; all 256 coolant values with active/inactive cut and eight speed boundaries; preservation of unrelated cut flags; every possible port value at both PAIR patch sites; and enabled/disabled authentication branches. The test reads the actual browser recipe, checks the original bytes, independently decodes each replacement jump, and exercises all shared cut-flag patterns, prior multipliers, and throttle-latch states. It confirms restoration without changing shared throttle state or existing ignition trim. Total: 78,354 selected-path cases.

`node scripts/test_tools.mjs` checks detected source states, both directions of editing, exact changed-byte sets, checksum correction, untouched boot bytes, unsupported and partial-patch rejection, strict re-import matching, and original-file preservation. These are software checks, not whole-ECU simulation or hardware qualification.

`python scripts/test_o2_control.py` adds 11,314 selected-path cases covering O2 fault creation, disabled-path suppression, neutral correction, actual serial reply packing and the injection/coil-charge distinction. Existing faults deliberately remain reportable. No test communicates with an ECU.

`python scripts/test_interlock_features.py` adds 25,344 selected-path cases for sidestand inhibition, fault 19, tip-over detection and fault 41 across all nine BINs. External relay and physical vehicle behaviour are not simulated.

## Dashboard pulse offset

[Dashboard speed output](SPEED_OUTPUT.md) documents the separate fixed −20 to +20 pulse offset and zero-output switch. The stateless constructor patch preserves zero input, clamps to 0–255, uses no persistent RAM and is verified across all nine registered BINs. This is not percentage scaling or a proportional sprocket correction.

## CO full-range override

**Enabled removes the CO correction's RPM fade-out; Disabled restores its stock curve.** This row controls the range of the dashboard adjustment, not the adjustment value itself. It changes neither spark timing nor the base fuel-table cells. Startup, other fuel corrections, output limits and fuel cuts still apply. On later applications, O2 feedback remains a separate correction and can influence the resulting mixture.

| Item | Early family | Late family |
|---|---|---|
| Curve descriptor | `34B0` | `3478` |
| Fifteen byte cells | `34B6–34C4` | `347E–348C` |
| Two changed cells for Enabled | `34C3–34C4`: `00 → FF` | `348B–348C`: `00 → FF` |
| Lookup and CO application | `800C–8031` | `768E–76A3` |
| Stored CO value in RAM | `09FC` (C1) | `0A00` |
| Speed / gain / scaled trim in RAM | `0900 / 09A0 / 095C` | `0920 / 099E / 0964` |
| Signed rounding helper | `8623–864D` | `7A2B–7A55` |
| Load and throttle fuel-lane consumers | `8323–83A0` | `7885–7902` |

Every registered image contains the same six-byte descriptor (`14 00 1C 00 00 80`) and stock cells (thirteen `FF` values, then two zeros), at its own family's addresses. The tool subtracts the loaded file's base address. It verifies the descriptor, lookup caller, signed-scaling helper and dashboard CO writer before allowing the toggle. Stock and all-`FF` curves are recognised; custom curves leave this control unavailable without discarding the user's map edits. Those custom cells can still be edited and re-imported through the ordinary map workspace. Unknown code or descriptor changes do not pass recognition.

The lookup clamps speed minus 5120 into 0–7168. Nodes are 512 speed-code units apart. Stock gain is 255 through speed code 11264, fades to zero near 11776, and holds zero above it. With all cells 255, it returns 255 for the entire 16-bit input domain, including above the last node. The new setting therefore removes the curve's fade-out without changing its axis or redirecting code.

For stored CO byte `C` and interpolated gain `G`, the centered correction is `sign(C−128) × floor((abs(C−128) × G + 128)/256)`. Four times that result is added to both normal fuel quantities before their gains and blend. Constant gain does not imply a constant percentage increase in final fuel. The early alternate load map, if selected, feeds the same corrected load lane.

`node scripts/test_co_tools.mjs` checks all nine image-specific layouts, the exact two-byte edit, checksums, restore/history, saved-file recognition, custom-map preservation and rejection of 800 individually corrupted lookup guards. `python scripts/test_co_override.py` executes 10,900 stock/override cases against the original CPU12 p-code, including both fuel lanes, every valid CO byte in both code families, speed transition points and upper clamping. Source instructions are checked against every BIN. These tests do not establish physical timing or bench-tested engine behaviour.
