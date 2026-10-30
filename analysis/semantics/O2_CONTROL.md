# O2 off: fuel maps, feedback and diagnostic faults

**O2 off does not select a different main fuel map in the registered late application.** It disables feedback eligibility and new O2 fault detection. The ordinary load/throttle fuel calculations and their other corrections continue. This conclusion comes from the setting's four code consumers and the downstream fuel calculation, not from an XDF label.

The [Tools feature controls](https://terrafirma2021.github.io/yamaha-xt660/tools/index.html#tune) expose the setting only for the four registered late-application BINs. The five early-application BINs have no configured feedback in their supplied calibration; their O2 row is disabled and read-only. Hardware behaviour has not been bench-tested.

## Direct master setting

CPU byte **`368E`**, file offset `1E8E` in a `0x1800`-based BIN, is `80` in all four registered late images. Each consumer explicitly requires `80`; the editor uses `00` for disabled and restores `80` for enabled.

| Consumer | With `368E != 80` |
|---|---|
| `6410–6415` in ADC channel 2 processing | Bypasses O2 fault-24 detection before setting current/history flags |
| `9800–9805` in feedback control | Branches to `98C3`, clearing feedback eligibility `099F:80` and its qualification counter |
| `99D5–99DA` | Bypasses upper-feedback-limit fault 31 |
| `9A48–9A4D` | Bypasses lower-feedback-limit fault 32 |

These are all direct reads of `368E` in the decoded late application. The supplied XDF's `466E` candidate is different: the traced path copies it into a serial-storage default. It is not used by this recipe.

## Which maps remain in use?

The main load table has cells at **`1B40`**, read through descriptor `1B2B` at `748C–7492` into RAM `0960`. The main throttle table has cells at **`2662`**, read through descriptor `264D` into `0962`. The regular speed, load, throttle and sensor-fault handling around these lookups remains intact. There is no `368E`-controlled branch selecting another base table.

The calculation subsequently derives `0CFE` and `0D00` from those quantities at `7645–7657`, applies the combined correction factors, and produces corrected quantities at `78BA–78C2` and the corresponding second path. O2 off leaves that calculation and the other compensation maps in place. It does not substitute an early-model calibration or load a second “O2 removed” map.

Two different kinds of feedback table must not be confused with those main fuel tables:

- Eligibility grids at `36C2` and `374E` decide whether feedback may operate. Master-off bypasses the checks before their results can enable feedback. Their cells remain unchanged.
- The adaptive trim grid at RAM `09BB–09CA` is a learned correction, not an alternate main fuel map. Feedback correction updates and the existing adaptive-reset configuration remain separate from base-map selection. The registered late images use `384F = FF` and `3856 = 80`, which take the existing grid-reset-to-`80` path at `9AF5–9B1B`. The patch does not erase external storage or rewrite that configuration.

### Neutral feedback correction

With `099F:80` clear, `994A–9952` loads `8000`. After the normal bounds checks, `99CB` stores that value to `097C`. The registered limits at `37D2/37D4` are `3333/CCCC`, so the neutral value is retained.

At `781B–7826`, `097C` is shifted right five times and contributes `floor(097C / 32) - 1024` to the combined correction calculation, before its next right shift. Thus `097C = 8000` contributes **zero** at that point. Calling this raw value a direct fuel multiplier would be misleading: it is centred correction arithmetic that feeds later scaled multiplication. The adaptive value at `097E` is also incorporated in the combined correction at `780C`; master-off does not invent or select a different base table for it.

## Fault detection, logging and the serial warning

Yamaha's [2007 XT660R/X supplementary service manual, printed pages 50 and 63–64](https://www.motomatrix.co.uk/yamaha-pdf/XT660X-R2007_Suppl_manual.pdf) identifies fault 24 as an abnormal O2 signal, 31 as feedback remaining at the lean compensation limit, and 32 as feedback remaining at the rich compensation limit. The ROM lookup and code agree with those identities.

| Fault | Current flag | History flag | Detection writers |
|---|---|---|---|
| 24 | `08B2:10` | `08BB:10` | `648B`, `6498` |
| 31 | `08B2:04` | `08BB:04` | `9A1C`, `9A29` |
| 32 | `08B2:02` | `08BB:02` | `9A8F`, `9A9C` |

These paths also set dirty flags `0BF4:40` / `0BF4:04` to request current/history persistence. Master-off skips creation of the corresponding flags and requests. It does not disable the generic logger, other sensor faults or the serial interface.

The ordinary fault scanner copies the current bitmap at `5C91–5CA0`, scans it with `5EA1`, and reads the fault number from ROM table `4695`. The result becomes `0B98`, is packed into reply byte `08AA`, and is included in the reply checksum. The O2 entries are `46A1 = 24`, `46A3 = 31`, `46A4 = 32`.

**Existing stored faults are retained.** Startup can reload current/history flags from external storage. Master-off prevents a newly disconnected sensor from generating a new O2 fault; it does not clear a fault recorded previously. The normal diagnostic history-clear procedure remains separate. Tests deliberately seed old O2 flags and confirm they are still reported with master-off, so this tool does not promise silence for an ECU with existing stored faults.

## Why the early O2 control is read-only

All five registered early images have variant `18D3 = 09` and zero-filled feedback eligibility grids at `35B0` and `363C`. Fault-24 detection skips this variant at `6BB3–6BB8`; the two trim-limit fault paths also skip it at `A744–A749` and `A7B7–A7BC`. The feedback calculation requires nonzero eligibility results at `A5A9–A5B9`, so the supplied grids prevent activation.

That establishes the supplied firmware configuration, not proof of which sensor is physically fitted to every motorcycle. Changing the variant to enable O2 would also change unrelated engine behaviour and is not offered.

## Reproduction

`python scripts/test_o2_control.py` checks source instruction bytes for each registered image and executes selected paths with the CPU12 interpreter. Its 11,314 cases cover:

- Positive controls that create current/history O2 faults, including counterfactual enabled diagnostic gates for the trim-limit faults.
- Disabled detection paths with all 256 input/flag byte values, preserving existing and unrelated faults.
- Neutral feedback restoration from eight prior correction values and all 256 eligibility flag values.
- Actual fault scanning, serial reply packing and reply checksum for faults 24, 31 and 32.
- Both early and late overrun injection gates versus normal coil-charge scheduling.

`node scripts/test_tools.mjs` additionally checks feature detection, supported-byte edits, exact byte differences, checksum correction, source preservation and re-import matching. The O2 patch changes only `368E` plus the editor's startup-checksum compensation. No fuel-map cell is changed.
