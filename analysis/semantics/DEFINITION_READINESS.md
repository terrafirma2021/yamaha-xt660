# Preparing an XDF or custom tool

The [operating-sequence review](OPERATING_SEQUENCES.md) closes the previously listed linked-sequence replay tasks for the early map set and post-start lifecycle in both families. It adds bounded pressure interleaving tests across all nine BINs. It does not establish absolute physical references, exhaustive whole-ECU behaviour or safe edited ranges.

The repository now includes a static research site, ready-made TunerPro definitions and flashing file checks, backed by image-specific evidence. It deliberately separates **byte layout**, **software behavior**, **physical interpretation**, and **validated editing**.

The [verification ledger](VERIFICATION_LEDGER.md) records each map and pin separately, including source review and outstanding sign-off requirements. A final **Verified** state must identify its exact claim; verified bytes or a matched MCU register do not imply a verified physical tuning definition.

## Definition fields

[catalog.json](catalog.json) contains exact offsets, widths, counts, byte order, stock bytes, descriptions and instruction references for 28 scalar/curve items. It also describes ADC and output identities. Existing [maps.json](../maps.json) and [axes.json](../axes.json) supply grid layouts and values.

| Field needed by an editor | Current state |
|---|---|
| Exact binary identity and length | Nine registered SHA-256 identities; four 65,536-byte files and five 59,392-byte files |
| CPU-address/file-offset translation | Recorded per image: CPU base 0 or 0x1800; file offset = CPU address minus base |
| Scalar width, endianness, unsigned/signed encoding | Recorded for the focused catalogue |
| Cell address, dimensions and axis storage | 699 image-specific maps / 69,575 cells; 71 layouts per early BIN and 86 per later BIN |
| Runtime selector / variant / alternate calibration | Documented where traced; incomplete globally |
| Conversion to Celsius, RPM, degrees, milliseconds, pressure | Clock/crank-conditional values and exact code/gain contributions are in the unit companion; Celsius, pressure and absolute BTDC remain unresolved |
| Reverse conversion and rounding policy | Raw XDF cell encodings are defined; estimated ignition displays in the research remain explicitly conditional |
| Valid physical adjustment ranges | Not inferred from the limits of a byte or word |
| Checksum algorithm and covered ranges | [ROM and serial algorithms](CHECKSUMS.md) recovered; [startup-corrected copy](CHECKSUM.md) tested. Flashing file preparation corrects and rechecks the startup sum; hardware programming validation is separate. |
| Flash format, programming procedure, boot requirements | [XT boot protocol and offline read assembly](../firmware/FLASH_TOOLING.md) recovered. Five BINs have populated boot; four have FF placeholders. Browser live read/write is not implemented or hardware-validated. |

`ready_for_tuning_export` is false for every current entry. This does not mean the offsets are guesses. It means the whole definition is not yet validated for engineering-unit edits and flash use.

## Important encoding details

- Fan set/clear thresholds use strict comparisons. A displayed “fan on” value must account for the fact that an internal value equal to the upper parameter does not switch it on.
- Period-based RPM cuts run in the inverse direction: higher speed means lower period. Their resume comparisons differ between the main and conditional limits.
- The temperature conversion has an implicit axis and a three-byte pointer bias; data start is not the loaded pointer.
- A timer request is not necessarily the same unit as a source map cell.
- A byte-wide MCU output register is not a calibration. RAM state should be observable in a future logger, not exposed as an editable ROM table.
- The secondary channel is disabled by the stock variant. Merely finding a second table/output is not evidence that it is used on this motorcycle.

## Implemented tools and their limits

The XDF library publishes generated definitions for every registered BIN. The [generator](../firmware/XDF_DEFINITIONS.md) reads the image-specific map catalogue and validates the source hash. Independent XML checks cover every source cell, dimension and file base. Native TunerPro captures verify representative 8-bit/16-bit edits in both file formats, plus all 1,350 copied cells from the early fuel table. Flashing file preparation checks a saved BIN and can produce a separate checksum-corrected copy.

`ready_for_tuning_export=false` means the full engineering-unit definition lacks physical/hardware sign-off. It does not mean raw XDF export is absent or that all raw addresses are uncertain. Feature patches have instruction tests, but those tests are not live ECU validation.

The website provides connection references; the Windows tool provides file inspection. The offline boot reader builds and verifies addressed blocks, but no live session or ECU read/write is implemented. [Flash tooling](../firmware/FLASH_TOOLING.md) separates recovered bytes from pending transport, timing and recovery work.

## Remaining work we can do from the repository

1. Extend the later transient-input lifecycle through output eligibility and timer edges. The [nine newly recovered curves](LATE_TRANSIENT_MAPS.md) now have actual-helper and pulse-arithmetic tests; the early linked-sequence tests do not cover that later lifecycle.
2. Trace residual calibration fields and indirect structures beyond known lookup helpers. Remaining layout bytes are 884 in the early family and 1,267 in the later family; these are not all unknown maps.
3. Reconcile scattered scalar findings into the focused catalogue, with precise byte ranges and consumer references.
4. Reconstruct the remaining boot session, retries, watchdog and recovery state machine, then exercise it with a simulated serial peer before live integration.

Physical work remains distinct: identify the fitted chip/clock, measure CPS phase against TDC and coil firing, establish temperature/pressure/TPS electrical transfer, confirm connector orientation/continuity and perform recoverable read/write/readback bench trials. The existing documents narrow these questions but do not provide all their answers. No additional user measurements are needed to continue the software tasks above.

## Reproducing the focused evidence

From the repository root:

```sh
python3 scripts/build_semantic_catalog.py
clang -std=c11 -O0 -fPIC -shared analysis/full/c/page_*.c analysis/full/c/dispatch.c -o /tmp/libxt660_full.so
python3 scripts/test_full_lift.py /tmp/libxt660_full.so
python3 scripts/test_control_semantics.py /tmp/libxt660_full.so
python3 scripts/fix_startup_checksum.py
python3 scripts/test_extended_maps.py /tmp/libxt660_full.so
python3 scripts/verify_semantics.py
```

The control fixtures use supplied ROM values and controlled RAM/register inputs. They check decisions and table results against the original instruction translation, not live ECU waveforms. Table-knot tests do not prove every interpolated point or physical scaling.

## Conditional engineering companion

[physical_units.json](physical_units.json) now provides per-map conversion status, named clock/crank assumptions, 64 numeric/logical/conditional cell interpretations, joint arithmetic for seven maps and nominal speed axes for 40 maps. [UNIT_DECODING.md](UNIT_DECODING.md) separates exact arithmetic from inferred physical scales and conflicting sensor evidence. An editor must display these assumptions and must not relabel relative spark angle as BTDC, treat load as measured kPa, or silently enable writes because a conversion is present.

The [consumer models](../../scripts/map_models.py) include word wrap, rounding, coupled saturation, asymmetric channel ordering and the stock half-scaling factor. Do not replace them with a single table-to-pulse multiplier. [Stock activation notes](MAP_CONSUMERS.md#active-versus-dormant-calibrations) also matter: some identified families are disabled by stock mode settings or zero eligibility cells.
