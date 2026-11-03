# Map inputs, inactive gains and eligibility gates

The new instruction replays resolve input formation and several previously open map-entry conditions. They do not establish sensor electrical transfer, mechanical crank phase or live interrupt timing. No source BIN was changed.

- [Input-coordinate replay](../firmware/input_coordinate_validation.json): **154,368 cases**, all nine registered BINs (five early, four later).
- [Map-entry replay](../firmware/map_entry_validation.json): **11,520 cases**, all five early-family BINs. These gates have not been transferred to the later family by similarity.
- Sources: [input test](../../scripts/test_input_coordinates.py), [entry test](../../scripts/test_map_entry_paths.py). Every executed instruction is checked against the corresponding BIN. Independent arithmetic/branch models are compared with CPU12 execution. Synthetic RAM and calibration fixtures exercise active, inactive, fault, saturation and boundary cases without modifying the files.

The [map resolution inventory](MAP_RESOLUTION.md) separates these results from remaining work. Immediate instruction traces, isolated arithmetic tests and complete state-sequence tests are different evidence scopes.

## Throttle source and learned closed reference

| Stage | Early family | Later family |
|---|---|---|
| ADC source block | `6A68–6A9B` | `62C7–62FA` |
| Raw 10-bit count | `08D0 = word[08CA] >> 6` | `08D6 = word[08D0] >> 6` |
| Fault mask / replacement word | `08AF:0C` / ROM `4E60` | `08B1:0C` / ROM `45FC` |
| Learned baseline | `08E0` | `08EA` |
| Relative count | `08E2` | `08EC` |
| Published scaled coordinate | `08CE` | `08D4` |
| Filtered relative count | `08E6` | `08F0` |
| Fuel-map axis | `08E8` | `08F2` |

Without a TPS fault, raw count comes from the ADC but the published coordinate comes from the separately serviced relative count, shifted left six. On a TPS fault the ROM replacement supplies both the raw count and the shifted published coordinate. They are not necessarily two views of the same instantaneous sample.

Early baseline learning (`8C3C–8C74`) counts consecutive calls where raw count is below the baseline. On the fourth qualifying call it lowers the baseline by one, floors at zero and clears the counter. Raw count at or above the baseline clears the counter. Relative count is `max(raw - baseline, 0)`.

The later block (`8034–80B5`) adds qualification: `abs(word[08E6] - 128) < max(0, word[4442] - 128)`, elapsed counter `B2C >= ROM[4444]`, and raw count below baseline. Four qualifying calls lower the baseline by one, bounded by ROM word `4446`. Counter `B2C` increments with saturation while its qualification holds and clears otherwise.

The relative-position filter uses:

```
step = floor(abs(target - previous) * gain / 256)
next = previous + step if target >= previous else previous - step
```

The movement latch changes only at an absolute difference of at least eight counts. The gain is ROM `1840` early / `1843` later. A capped copy, `min(filtered_relative, 255)`, feeds throttle threshold comparisons (`08EC` early / `08F6` later).

The fuel-map axis has a separate tracking filter, gain ROM `1841` / `1844`. If the hold counter `B03` / `B36` is below ROM `19D8` / `19B2`, it copies the published coordinate directly. The early startup branch also initializes both fuel-related throttle filters directly from `08CE`.

**Resolved:** learning direction, qualification, count offsets, clipping, filtering and TPS fault replacement. **Still physical:** counts per degree and throttle geometry. A firmware coordinate does not by itself establish percent throttle.

## History change is a position difference

Early `8EA2–8F1B` computes:

```
08ED = clamp(128 + filtered_relative - history[index], 0, 255)
history[index] = filtered_relative
index = (index + 2) & ROM[1842]
```

All supplied images use mask 7 (later equivalent ROM `1845`), giving four word samples. The six early transient response curves `34D0/34DA/34E4/355D/3567/3571` therefore have an exact internal axis interpretation: **raw − 128 relative TPS counts over four serviced samples**, with saturation at both ends. Their ideal uniform knots can extend beyond the header's clamped input range; an ideal knot is not necessarily a reachable input.

The later history block `82DC–834C` preserves an extended word: `08F8 = clamp(128 + current - historical, 0, 1151)`. A second byte `08FA = min(08F8, 255)` serves other gates. This family difference must be retained when tracing consumers; the early clipped-byte axis must not be copied blindly to a later map.

The base scheduler compares elapsed TCNT against 2,500 timer ticks (`679C–67B2` early; corresponding late update ends at `5FEF`) and posts the task flag. With the conditional 500 kHz timer profile this is nominally 5 ms, making four serviced samples nominally 20 ms. Cooperative task servicing and coalesced flags mean that this is **not a guaranteed wall-clock history interval**. These coordinates are changes, not already normalized degrees/second.

## Load-change gain maps are inactive in every supplied BIN

Early `7833–78BC` compares the high bytes of load source `0C8C` and filtered state `08F0`. Later `7030–70B2` uses `0CAE` and `08FE`. The filter uses a neutral/non-neutral selected gain, and copies its source while the stale counter is below 100.

The magnitude of the high-byte difference is capped at **127**. A signed code is centered on 128; if magnitude is less than or equal to the deadband, the qualified code becomes 128 and the working magnitude becomes zero.

All nine supplied BINs store deadband **255**: early ROM `3344`, later ROM `330C`. Thus the magnitude always falls inside the deadband. The six load-change gain curves in each BIN have **zero contribution in the stored configuration**, even when their cells are nonzero. Changing their cells alone cannot activate them.

| Family | Gain map IDs | Qualified delta / magnitude |
|---|---|---|
| Early | `delta_0989_gain_1` through `_6` | `0989` / `0DDF` |
| Later | `table_33bf`, `table_33d6`, `table_33ed`, `table_3404`, `table_341b`, `table_3432` | `0987` / `0E63` |

Replay exercises both stored and modified synthetic deadbands, proving the dormant calculation as well as its stock inhibition. These are differences in an internal processed load coordinate, not kPa/second.

## Qualified throttle change

Early `793D–7A2F` filters published throttle into `08EA`, then compares its high byte with fuel-axis `08E8` (including the optional baseline adjustment). Later `7128–7213` uses `08F4` and `08F2`. The magnitude cap is 127; the output is centered on 128.

The result is suppressed when the high-byte axis reaches the configured limit, while the stale counter is below 100, or inside the deadband. Counter/hold and optional-baseline branches are included in replay. Early stock limit is 184 (`3340`), deadband 2 (`3341`). Later counterparts are `3308/3309`. The qualified bytes are `0985` early / `0983` later.

The gain-cell scale is already **normalized fuel percentage points per raw delta count**, before the sign-dependent coolant factor and further gains. No division by elapsed time occurs in this coordinate; assigning a physical rate would change its meaning.

## Supply source and filtering

Early `6EBB–6ECA` publishes ADC-high-byte supply code `08D9`; fault `08B1:04` substitutes 154. Later `6770–677F` uses `08DF` and fault `08B3:04`, with the same replacement.

Early `9EEE–9F19` / later `9371–939C` track `effective_byte * 256` with the signed Q8 filter above. Startup flag `0881:10` copies directly. Filtered word is `08DA` early / `08E0` later. Injector compensation uses its high byte; dwell uses the effective supply byte directly. The electrical divider and ADC reference are still required to name volts.

## Early map-entry and override gates

### Throttle quantity fallback

`7DE6–7E04` substitutes ROM `4E62` **only if both** `(08AF & 0C) != 0` **and** `(08AF & 30) != 0`. A TPS-only or pressure-only fault keeps fuel-axis `08E8` at this point. This does not remove the earlier TPS source replacement described above. All 256 fault-byte values are replayed for each early BIN.

### Feedback startup delay

`6B49–6B74` skips the gate during `0881:10`. Otherwise `09A1:10` bypasses the delay; without that bypass ROM `18B5 == 128` inhibits lookup/setting. If eligible, counter `0CAF >= looked-up threshold` sets `09A1:40`. This block does not clear the bit. Tests cover the bypass, disable, startup and exact threshold boundary.

### Adaptive grids and coolant delay

`A564–A63A` requires both `35B0` and `363C` grids nonzero. Every supplied early image has all-zero cells, rejecting the normal eligibility path. Synthetic active grids expose the remaining gates:

- Startup `0881:10` clear; elapsed `09B5 >=` coolant-selected delay `09B4`; coolant at least ROM `357E`.
- `0886:40` clear, `09A1:40` set, post-start word `0992 == 0`, transient byte `097A == 128`.
- Variant 9 must be outside the neutral-input branch.
- Fault masks `08AF:3C`, `08B0:C0`, `08B1:C0` clear; `08A0:20` clear.
- Centered word `0982` between ROM `3580` and `3582`, inclusive.
- Pressure hysteresis bit `09A2:80` set: pressure `08F2 >= ROM[3586]` sets it, `<= ROM[3584]` clears it, and the band retains its previous state.

When these qualify, counter `09AD >= ROM[357D]` sets `09A1:80`; otherwise the bit clears. An ineligible state resets the counter, whereas a qualified state still waiting for the count does not reset it. This gate is distinct from the downstream transition step arithmetic in [MAP_CONSUMERS.md](MAP_CONSUMERS.md).

### PAIR grids

`9CAE–9D61` bypasses the normal update when diagnostic flag `08A0:04` is set and `BDD == D49`; the current counter and command are retained. Outside that bypass, non-9 variants clear the command.

For variant 9, normal qualification requires coolant at least ROM `4C03`, post-start word `0992 <= ROM[4C04] << 8`, centered state `0982 <= word[4C06]`, flag `0881:20` clear, the selected neutral/ratio enable byte nonzero, and both grids `4C44/4D48` nonzero. Counter `0ACF` increments with saturation on qualification, otherwise clears. The command's delay test uses the **old** counter against ROM `4C02`, before the increment.

Separate fallback branches set the command if `09A1:80`, `08A0:20`, `08B0:16` or `08B1:C0` is present. Replay checks port `PTP:02` and state `0889:80`; it does not measure actual coil energization or confirm the PCB route.

## Existing evidence retained

The [speed-source replay](../firmware/speed_source_validation.json) and [fuel-mode replay](../firmware/fuel_mode_validation.json) already cover both families. Pressure and alternate source work is described in [PRESSURE_ESTIMATE.md](PRESSURE_ESTIMATE.md). Cell consumers and selectors are recorded in [MAP_CONSUMERS.md](MAP_CONSUMERS.md) and [MAP_SELECTORS.md](MAP_SELECTORS.md).

Remaining software work is now named per map: integrated transient trigger/accumulator/scheduling, post-start lifecycle, special injection dispatch, and the early alternate ignition sequence. Remaining hardware work includes electrical sensor scales, actual timer frequency, mechanical crank/TDC reference and edited-output testing. Passing these new replay fixtures is not a full-engine bench sign-off.
