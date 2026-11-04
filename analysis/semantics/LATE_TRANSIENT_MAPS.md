# Nine later transient-fuel curves recovered in the repository audit

The previous later-family catalogue omitted a second lookup implementation. It recognised helpers at `BBAA/BBCF/BCC4` but did not follow `EE81/EF7F/EF3A` or axis helper `EFA4`. These are real instruction-referenced curves, not structures inferred from their byte patterns.

All four later BINs now have **86 maps / 7,050 cells**. The complete nine-image catalogue has **699 map records / 69,575 cells**. These counts include repeated layouts across images.

| Cell address | Points | Input | Role in the recovered calculation |
|---|---:|---|---|
| `3570` | 8 | `0912`, axis `3560` | Neutral response |
| `3578` | 8 | `0912`, axis `3560` | Normal ratio response |
| `3580` | 8 | `0912`, axis `3560` | Upper ratio response |
| `359A` | 9 | `090C`, axis `3588` | Sampled-input correction |
| `35A6` | 29 | Coolant code `0914` | Coolant gain |
| `35C6` | 25 | Intake-temperature code `0915` | Temperature gain with an additional 384 in the consumer |
| `35E6` | 8 | Pressure estimate `0900` | Pressure gain |
| `35FE` | 8 | Speed code `0920`, axis `35EE` | Speed correction |
| `3618` | 9 | Change code `0910`, axis `3606` | Change correction |

All addresses are CPU addresses. Later BIN files start at CPU `1800`; their file offsets are therefore CPU address minus `1800`.

## Exact arithmetic and selection

The calculation at `E238–E383` multiplies pressure and coolant lookup outputs, then applies `(intake-temperature output + 384) / 256`. Speed and change corrections each introduce another division by 256. Each of those intermediate products saturates at 65,535.

Neutral flag `088F:80` selects `3570`; otherwise `089A <= ROM[355F]` selects `3578`, and the remaining branch selects `3580`. The selected response and sampled-input correction multiply the intermediate result; division by 4,096 produces the pulse contribution, capped at **25,000 timer ticks** in `0A1E`. Supply compensation `0966` is added with 16-bit saturation to form `0A1C`. Flag `0A27:08` records that the calculation completed.

`EFA4` clamps the stored axis, searches its interval and rounds its fractional index. `EF3A` returns the byte-cell interpolation in Q8 form; callers add 128 before taking the high byte. Uniform helpers return the truncated byte interpolation. These rounding differences are retained in the independent test model.

## Entry and output are separate decisions

The immediate calculation gate requires port bit `0020:20` clear, phase `0942 == ROM[355E]`, and captured-pair flag `0A27:10`. The earlier block additionally depends on copied configuration `ROM[1846] -> 0E05` and successful sampling. `E142–E21A` constructs the sampled/filtered values and phase-separated change; assigning mechanical or electrical units to those codes requires more evidence.

The downstream block `E387–E408` has separate enable, phase, speed, sampled-input and pulse thresholds plus inhibit flags. It can call `EEBD`, whose timer path consumes `0A1C`. The new fixtures stop before that output gate: a calculated pulse is not proof that an injector event occurs. Existing early-family operating-sequence tests must not be treated as validation of this later path.

## Verification and remaining work

[The replay report](../firmware/late_transient_validation.json) records **9,816 checks** across all four later BINs, with **294 instruction addresses checked against each image**. It covers the actual four helpers, axis boundaries, fractional interpolation, non-flat synthetic cells, all three response selections, immediate entry gates, integer saturation and supply compensation. Original BINs are unchanged.

Run `python scripts/test_late_transient_maps.py --check` locally. The manual regression workflow includes it; the Pages workflow only checks report provenance and builds/checks the website.

Still needed: replay the complete sampled-input lifecycle through its downstream output gates and timer edges, including interrupted operation; establish physical input/timer references; validate edited behaviour on the identified hardware. This finding also demonstrates why zero unmatched calls to a *known* helper list is not proof that every map has been found. The structured-looking residual at `19AE–1AAA` is not promoted to a map without a caller.
