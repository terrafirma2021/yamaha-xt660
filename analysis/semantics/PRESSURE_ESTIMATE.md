# Pressure sampling, estimation and fuel-map load

Six curves use RAM `08F2`: startup pressure gain (`19C6`), transient pressure gain (`353A`), load/throttle fuel pressure gains (`323C`, `32E0`), spark bound (`4BAC`) and pressure-to-load gain (`1854`). This input is a selected, clamped state, not the diagnostic pressure byte and not automatically kPa.

[pressure_state.py](../../scripts/pressure_state.py) models the early selection and tracking blocks. The subsequent [cross-family instruction replay](../../scripts/test_pressure_sources.py) adds acquisition-result storage, the complete five-sample eligibility block, stock load-sample selection, both normalization paths and the intervening filter. Its [23,904 passing cases across all nine BINs](../firmware/pressure_source_validation.json) establish the integer transfer at those boundaries. They do not establish analog calibration or complete ECU scheduling.

## What supplies the load axis

The selected pressure estimate and the fuel-map load coordinate have different jobs. Under the stock configuration, the first comes from five pressure-history samples; the second starts from a different sample, passes through a filter, then uses a gain indexed by the estimate. The later firmware uses different RAM addresses and different unsynchronized-sample handling.

| Stage | Early family | Later family |
|---|---|---|
| Latest pressure ADC result consumed by this path | `08CC` | `08D2` |
| Phase-indexed histories | `C42`, `C58` | `C64`, `C7A` |
| Five-sample estimator function | `869E–87E6` | `7A63–7BAB` |
| Selected/clamped pressure estimate | `08F2` | `0900` |
| Selected load sample | `C8A` | `CAC` |
| Filtered load sample | `C8E` | `CB0` |
| Normalized, filtered map-load coordinate | `C90` | `CB2` |
| Normalized, unfiltered coordinate | `C8C` | `CAE` |
| ROM gain curve / RAM copy | `1854` / `DBA` | `185A` / `E32` |

### Acquisition-result storage

`E385–E3BE` / `DCC1–DCFA` consume the stored ADC result. If `088D:02` is set, they leave the histories untouched. Otherwise, with synchronization flag `BFE:80` / `C20:80` set, they store the sample at `short_history[phase]` and `long_history[cycle & 31]`, and update `C40` / `C62`. Without synchronization, both writes use slot zero. The fixtures cover all 11 ordinary phase positions and all 24 cycle positions, synchronized/unsynchronized and successful/failed result paths. They inject the stored result; they do not simulate the ADC's electrical conversion or prove that every possible counter value is valid.

### Five-sample acceptance and tracking

The estimator copies five consecutive words from long-history index **14 through 18** in every supplied BIN. It computes maximum and minimum before deciding whether to update. The update is accepted only when all these conditions hold:

| Condition | Stock requirement in all nine BINs |
|---|---|
| Fault flags `08AF` / `08B1` | Mask `3C` clear |
| Replacement flag `089F` / `08A1` | Bit `80` clear |
| State flag `0881` | Bit `10` clear |
| Five-sample spread | Maximum − minimum **≤ 384** |
| Throttle coordinate `08E8` / `08F2` | **734–11008**, inclusive |
| Speed coordinate `0900` / `0920` | **4096–23040**, inclusive |
| Current map-load coordinate `C90` / `CB2` | **27520–65280**, inclusive |

These are internal coordinates. The speed window corresponds to nominally 800–4500 rpm under the separately stated clock/crank profile; that conversion is not needed to test the comparisons. Rejected updates still refresh the five copied samples and extrema, but retain the previous mean and tracked estimate. Accepted updates use the mean and `255/256` tracking formula below. Equality at every bound is tested, along with the immediately adjacent rejected values.

### Which pressure sample supplies load

The load selection block runs at phase zero, or phase one when the phase setting equals `80`. Both families select **one sample at long-history index 6** under their stock synchronized load mode (`CA8:01` / `CCA:01`). Fault mask `30` substitutes the configured fallback word before normalization.

Without that mode, the families differ:

- Early `E475–E483` copies the separately maintained `C88` into the selected load sample and its secondary filter target.
- Later `DDB1–DDC8` retains the previous target unless `CCA:08` requests a refresh. A refresh clears that request and samples the short history instead, using the same configured index 6. `DFCC–DFE7` can arm this request when synchronized, outside the long-history mode, after the phase comparison has fallen.

Both families also contain configurable multi-sample modes. The new acquisition fixtures verify the stock one-sample configuration, not every dormant multi-sample combination. The later weighted loop must not be treated as byte-for-byte equivalent to the early unrolled code.

### Exact pressure-to-load transfer

All nine images contain the same curve header and 21 cells. Its input minimum is 29184, span 20480, and knots are separated by 1024 estimate counts. Both lookup helpers interpolate with the firmware's integer fractions. The stock load filter gain is **64/256**:

```text
filtered = previous + sign(sample - previous)
                    * floor(abs(sample - previous) * 64 / 256)
gain = pressure_to_load_curve(selected_pressure_estimate)
delta = floor((abs(filtered - 7863) * 2 * gain + 128) / 256)
map_load = clamp(7863 + sign(filtered - 7863) * delta, 0, 65535)
```

`95A6–9661` / `8A05–8AC0` perform that filtered transfer. `EA1B–EA7F` / `DF0E–DF72` apply the same lookup and signed rescale directly to the unfiltered selected sample for `C8C` / `CAE`. The early second consumer was previously labelled an “unreferenced path” in the map dossier; it is a continuation of the sampled-load path, and its arithmetic is now replayed explicitly.

A curve cell of **128 is unity around origin 7863**. It is not an additive pressure correction and it does not mean 128 kPa. The curve approximately compensates inversely for its pressure-estimate input: at its knots, `(input−7863)*cell/128` ranges from about 39603 to 40120. That numerical pattern supports a normalization interpretation, but does not identify an absolute pressure reference. The diagnostic conversion uses a separate origin, **7872**, and must not be substituted into this calculation.

## Priority at B304–B381

The first matching row wins. Conditions name raw flags without inventing a hardware meaning for every bit.

| Priority | Condition | Selected word | Side effect |
|---|---|---|---|
| 1 | `B3B <= ROM[1843]` and `0880 & 08` | `0DA8` | Set B3B to 255; replace tracking words |
| 2 | `089F & 08` | `0DA8` | Clear that request bit; replace tracking words |
| 3 | `08AF & 3C` | `0DA8` | Replace tracking words |
| 4 | `089F & 80` | `0CA4` | Replace tracking words |
| 5 | `ROM[186F] == 80` | `0CC8` | Keep tracking words |
| 6 | Otherwise | `0CB6` | Keep tracking words |

Replacement writes the selected word to `CB4`, `CB6`, `CC6`, `CCA` and `CC8` before clamping. The selected value is clamped by the ordered comparisons against ROM words `18AC` and `18AE`, then stored in `08F2`. B3B increments with saturation at 255.

Stock values are selector **128**, startup counter threshold **12**, lower clamp **27,520 (`6B80`)**, upper clamp **65,280 (`FF00`)**. Thus the normal stock path selects **CC8**, not CB6. The limit comparison is inclusive at both ends; the initialization and replacement values retain their separate provenance. Initialization at `5261–5274` copies `0E40` into this state family.

## Stock tracked state at 8764–87E2

After the upstream eligibility gates accept an update, the code averages five words at `CB8`, `CBA`, `CBC`, `CBE`, `CC0` with a 24-bit sum. It then moves the previous CCA toward that mean using the byte at `189E`:

```text
mean = floor(sum(five_samples) / 5)
step = floor(abs(mean - previous_CCA) * ROM[189E] / 256)
current = previous_CCA + step   if mean >= previous_CCA
          previous_CCA - step  otherwise
CC6 = mean
CCA = CC8 = current
```

Stock gain is **255/256**, with truncation of the magnitude toward zero. This is a stateful accepted-window update, not a new affine sensor conversion. The original isolated fixture starts after the gates; the cross-family fixture above now exercises the complete eligibility block as well.

The later selected-estimate path at `AA41–AAAC` has the same fallback/replacement priority and the same final limits, but directly selects `CE2` in the normal case. It does **not** retain the early `ROM[186F]` choice between two tracking algorithms. Copying that early selector interpretation into a later BIN would be incorrect.

## Verification scope and what remains

The selection fixture covers all **65,536 request/fault byte pairs**, all **65,536 candidate words through each of the two normal sources**, and **8,000 randomized threshold/limit cases**: 204,608 selection checks. Another **8,192 cases** test the five-sample mean, both signs of the tracking filter, all gain-byte values and large sums. Total: **212,800 passing cases**.

The cross-family pass adds 23,904 checks: 9,504 acquisition-result storage cases, 1,152 window-gate cases, 2,304 tracking cases spanning all gain bytes, 4,689 source/limit cases, 1,152 load-selection cases and 5,103 lookup/filter/normalization cases. Every executed instruction is compared with the respective BIN's bytes. Synthetic boundary values also exercise rounding and saturation outside normal operating conditions; they are not tuning recommendations.

The remaining physical-scale gap is the sensor/circuit transfer and absolute pressure reference, not the stock filter's arithmetic. Dormant weighted sample modes, the complete interrupt/task timing interaction, and the physical meanings of every eligibility flag also remain outside this fixture's coverage. The load normalization feeds the [family-specific fuel correction and request chains](MAP_CONSUMERS.md#fuel-transfer-checked-in-both-firmware-families).

Reproduce with `python3 scripts/test_pressure_state.py /path/to/libxt660_full.so`. Original and checksum-corrected firmware files are unchanged.

Reproduce the new family pass with `python3 scripts/test_pressure_sources.py --check`; it does not require a compiled library or ECU connection.
