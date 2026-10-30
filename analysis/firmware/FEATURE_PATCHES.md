# BIN feature controls

The [Tools page](../../tools/index.html) detects feature states from the loaded bytes. Each feature has **Enabled / Disabled** radio buttons. Unsupported controls and controls without an identified BIN are greyed out. Source files remain untouched. Changes, undo and reset use a draft with automatic startup-checksum compensation; exported reports include feature states and byte differences.

These recipes are instruction-tested against all nine registered BINs. **No patched ECU has been bench-tested.** An enabled PAIR control means the firmware may command the valve; it is not a live valve reading. Early applications without configured O2 feedback show that row disabled and read-only. Unexpected patch bytes remain unavailable.

## Supported recipes

All addresses below are CPU addresses. For a 59,392-byte BIN, subtract `0x1800` to obtain the file offset. The tool handles this automatically.

| Feature | Early application | Late application | Disabled state |
|---|---|---|---|
| Immobilizer | `4E7D` → RAM `0DD5`, copy at `61DE` | `4619` → RAM `0E4D`, copy at `58DF` | `00 → 80` |
| PAIR valve command | `9D5A` and `BAC3`, PTP bit 1 | `91EF` and `A465`, PTP bit 0 | Replace opcode `4C` (BSET) with `4D` (BCLR), keeping operands |
| Overrun cut | `348A`: `90 → FF` | `3451`: `7D → FF` and `3456`: `85 → FF` | Impossible entry condition plus restoration of the cut multiplier |

| O2 feedback and new O2 faults | Not configured in the registered early images; read-only | `368E`: `80 → 00` | Bypass feedback eligibility and faults 24/31/32 |
| Sidestand ECU cut-off | `CC5E`: `1C → 1D`; `4E6C`: `00 → 80` | `C2C4`: `1C → 1D`; `4608`: `00 → 80` | Prevent the shared inhibit assertion and new fault 19 |
| Lean-angle cut-off | `4E91`: `00 → 80` | `462D`: `00 → 80` | Bypass tip-over detection and use the fault-41 clear path |

Enabling restores the recipe's original registered bytes. A partial patch or unexpected parameter is unverified, not guessed to be enabled. Imported files with only these recognised changes and checksum compensation can be matched byte-for-byte against registered references outside those positions. That is labelled a recognised feature-edited layout, not an exact source identity. Files with other edits remain inspection-only on re-import.

### Immobilizer

Early `A9AF` and late `9CF1` compare the copied configuration with `80` and bypass authentication when equal. Startup and serial paths also consume this configuration. Existing owner and immo-off images therefore display Disabled without trusting filenames. The late immo-off source also differs at `4751`; this additional byte is preserved, not used as the authentication-state detector. Re-enabling restores authentication code behaviour; it does not create or pair keys.

### PAIR valve

Both normal control and the diagnostic actuator command must be covered. Early `9D5A` / `BAC3` assert `F0:02`; late `91EF` / `A465` assert `F0:01`. These are different GPIO bits between families. Replacing both assertions with clears covers the direct assertion writers in the decoded application. Startup initialises these bits clear, and the existing off/failsafe paths clear them.

Zeroing the air-induction grids alone is insufficient: fault/mode override paths can still reach the assertion. This recipe changes the commands instead of those grids. Physical output voltage and valve operation still need hardware verification; firmware status bookkeeping may continue to report a requested on-state.

### Deceleration fuel cut: thresholds, not a main fuel map

Early `765D–77B1` and late `6E6B–6FC6` evaluate coolant, runtime age, speed hysteresis, throttle/load qualification, delays and neutral state. They set RAM `0886:40` and write zero to the fuel multiplier `097A` when cutting. The normal injection dispatcher consumes the cut state. This is separate from rev-limit cut logic.

For the early code, entry requires the 8-bit coolant code to be **strictly greater than** byte `348A`. Setting the threshold to `FF` makes entry impossible. Its exit path clears the deceleration flag and writes `80` to multiplier `097A`, including when the cut was already active.

The late coolant comparisons differ, so the same one-byte recipe is not portable. Late entry requires the 8-bit runtime-age byte to exceed `3451`; setting it to `FF` prevents entry. Setting exit threshold `3456` to `FF` ensures `097A` returns to `80` even after an active cut. Both changes are needed for the tested restoration path. This is not the XDF's blanket eight-byte `FF` patch.

No RPM limit, other fuel-cut flags, ignition timing table or spark-cut limiter is altered. Deceleration ignition correction/recovery is not evidence of a separate spark-cut switch.

## O2 feedback and diagnostic reporting

The late application has a verified master setting at `368E`. Disabling it bypasses feedback eligibility and the detection paths for faults 24, 31 and 32. This prevents new current/history flags and their log-update requests; it does **not** erase existing faults or hide them from the serial reply. The stock early BINs use variant 9, skip these fault paths and contain zero feedback eligibility grids, so no enable patch is offered for them.

The previous XDF candidate at `466E` remains excluded: it affects a serial-storage default and has not been established as the master O2 control. The new recipe uses the directly consumed `368E` flag instead.

See [O2 control, fuel maps and fault reporting](../semantics/O2_CONTROL.md) for the consumer addresses, neutral correction calculation, retained base fuel maps, stored-history limitation and manufacturer fault definitions.

## One overrun control

The page now shows one **Overrun cut** row. The shared deceleration flag affects injection and linked ignition corrections, but it is not itself a normal coil-charge inhibit. Selected-path execution with `0886:40` both clear and set proves that injection is gated while coil charging can still be scheduled. Separate rev-limit fuel/spark cut flags remain untouched. Combining the UI row does not equate fuel cut with suppressing every spark.

## Reproducible checks

[Sidestand and lean-angle controls](../semantics/INTERLOCK_CONTROLS.md) document the two interlock recipes, their source paths and physical limitations. The sidestand patch does not change the external starting relay. The lean-angle patch is not a blanket erase of existing trip latches or stored faults. No clutch switch is provided in the editor.

`python scripts/test_feature_patches.py` executes selected CPU12 paths using byte-checked disassembly for both families and all nine registered BINs. It includes a stock positive control that enters fuel cut; all 256 coolant values with active/inactive cut and eight speed boundaries; preservation of unrelated cut flags; every possible port value at both PAIR patch sites; and enabled/disabled authentication branches. Total: 41,490 selected-path cases.

`node scripts/test_tools.mjs` checks detected source states, both directions of editing, exact changed-byte sets, checksum correction, untouched boot bytes, unsupported and partial-patch rejection, strict re-import matching, and original-file preservation. These are software checks, not whole-ECU simulation or hardware qualification.

`python scripts/test_o2_control.py` adds 11,314 selected-path cases covering O2 fault creation, disabled-path suppression, neutral correction, actual serial reply packing and the injection/coil-charge distinction. Existing faults deliberately remain reportable. No test communicates with an ECU.

`python scripts/test_interlock_features.py` adds 25,344 selected-path cases for sidestand inhibition, fault 19, tip-over detection and fault 41 across all nine BINs. External relay and physical vehicle behaviour are not simulated.
