# BIN feature controls

The [Tools page](../../tools/index.html) detects feature states from the loaded bytes. A checked control means **enabled**, not “disable enabled”. Source files remain untouched. Changes, undo and reset use a draft with automatic startup-checksum compensation; exported reports include feature states and byte differences.

These recipes are instruction-tested against all nine registered BINs. **No patched ECU has been bench-tested.** An enabled PAIR control means the firmware may command the valve; it is not a live valve reading. Unresolved features display **Unverified** with editing unavailable.

## Supported recipes

All addresses below are CPU addresses. For a 59,392-byte BIN, subtract `0x1800` to obtain the file offset. The tool handles this automatically.

| Feature | Early application | Late application | Disabled state |
|---|---|---|---|
| Immobilizer | `4E7D` → RAM `0DD5`, copy at `61DE` | `4619` → RAM `0E4D`, copy at `58DF` | `00 → 80` |
| PAIR valve command | `9D5A` and `BAC3`, PTP bit 1 | `91EF` and `A465`, PTP bit 0 | Replace opcode `4C` (BSET) with `4D` (BCLR), keeping operands |
| Deceleration fuel cut | `348A`: `90 → FF` | `3451`: `7D → FF` and `3456`: `85 → FF` | Impossible entry condition plus restoration of the cut multiplier |

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

## Unresolved controls

**O2 sensor / feedback:** the supplied 2008 XDF names file offset `2E6E` (`466E` CPU) as an O2 disable, changing `01 → 00`. The traced indexed path `502D` copies this byte into staging RAM `0E5D`, then writes through the serial-storage helper `4FBF` to storage command address `0A07`. The direct path is a stored default, not a demonstrated live feedback-enable gate. A complete link through stored state, feedback eligibility and sensor fault handling has not been established. Offering it as a complete O2 disable would overstate the evidence.

**Deceleration spark cut:** a separate switch has not been identified. Fuel-cut gating, ignition corrections and rev-limit spark cuts must not be collapsed into one control. This row remains unverified.

## Reproducible checks

`python scripts/test_feature_patches.py` executes selected CPU12 paths using byte-checked disassembly for both families and all nine registered BINs. It includes a stock positive control that enters fuel cut; all 256 coolant values with active/inactive cut and eight speed boundaries; preservation of unrelated cut flags; every possible port value at both PAIR patch sites; and enabled/disabled authentication branches. Total: 41,490 selected-path cases.

`node scripts/test_tools.mjs` checks detected source states, both directions of editing, exact changed-byte sets, checksum correction, untouched boot bytes, unsupported and partial-patch rejection, strict re-import matching, and original-file preservation. These are software checks, not whole-ECU simulation or hardware qualification.
