# Repository audit — 4 November 2026

Scope: all nine registered BINs, both application families, extracted maps, stored evidence, pin applicability, XDF generation and file preparation, desktop flash tooling and generated website. This is a repository/software audit, not a physical ECU certification or a claim that every instruction path has been exercised.

## Findings fixed

1. **Nine later-family curves were missing.** The catalogue did not follow a second set of lookup helpers. Added the curves, axes, caller references and image-specific values for all four later BINs. [Detailed finding and arithmetic](semantics/LATE_TRANSIENT_MAPS.md). The actual helpers and pulse calculation pass 9,816 new byte-checked instruction fixtures.
2. **Readiness documentation was stale.** It described a future viewer/exporter and absent boot content as if those statements applied to the whole repository. [Definition readiness](semantics/DEFINITION_READINESS.md) now distinguishes the generated XDFs, populated versus missing boot, and the software-tested desktop transport whose bench validation remains pending.
3. **Residual-byte labels overstated what was unknown.** The access inventory previously labelled every scalar missing from its small focused catalogue as unresolved, including fields traced in newer documents. It now says `static_access_not_in_focused_catalog`. This fixes the claim; it does not silently certify those fields or finish the scalar catalogue.
4. **Summary counts had drifted.** Updated map/cell totals and the original-image instruction-linked pin count. Existing map bytes, axes and original firmware files are unchanged. The pressure gain copied to RAM also gains its previously omitted second helper call in the evidence.

## Checked locally

| Area | Result and scope |
|---|---|
| Source files and identities | All nine registered SHA-256 identities and the supplied dataset inventory checked; original BINs preserved |
| Application families | Every exported instruction matches the relevant image; early/later code, embedded regions, maps and axis spans checked |
| Map extraction | 71 maps / 8,275 cells per early BIN; 86 maps / 7,050 cells per later BIN; **699 records / 69,575 cells** total |
| Lookup and consumer tests | Existing lookup, source, mode, entry, operating-sequence and pressure-preemption tests rerun; new later transient helper/caller tests pass |
| Native lifted model | All eleven native-model test programs rerun, including instruction differential, controls, maps, units, sensors, crank, connector, pressure and spark scheduling |
| Pins | All 80 reference package positions retained; 53 instruction-linked positions in FF-boot images, 56 where populated-boot evidence is available; family and configuration checks pass |
| XDF and file checks | Raw cells, image-base translation, big-endian encoding, checksum correction and all 699 generated XML tables checked; native 8-bit/16-bit edits checked in both BIN formats, with all 1,350 copied cells of the 16-bit table verified ([record](firmware/tunerpro_capture.json)) |
| Flash tooling | Desktop session/read/write/readback implementation passes 143 byte-stream checks across all nine input layouts; file checks cover 427 XDF presets. YamahaFlasher identity, 50 static anchors and boot session record rechecked without launching it. No physical ECU test |
| Website | Static build, content, map pages, links, profile/firmware routing, NoScript content and same-origin script checks run locally before publication |
| Publishing | Full firmware regression remains manual-only in GitHub; Pages performs provenance and website checks, not the full replay suite |

Two preserved source images have startup sum `AAD5`: the original 2005 dump and the supplied 2C1-00 immobilizer-off file. The other seven have `AA55`. The original's separately registered corrected copy has `AA55`; editing/export tests verify automatic correction. A failing source checksum is not hidden by altering the evidence file.

The exact new results are in [late_transient_validation.json](firmware/late_transient_validation.json); image/layout accounting is in [family_verification.json](firmware/family_verification.json), and scoped evidence is indexed by the [verification ledger](semantics/VERIFICATION_LEDGER.md). No new physical sign-off is awarded by this audit.

Native export integration was checked after this audit: TunerPro 5.0.9786 imported representative early 65,536-byte/16-bit and later 59,392-byte/8-bit definitions. Saved edits changed only their expected bytes. All 1,350 copied cells of the early table match. [Capture record](firmware/tunerpro_capture.json) and [reproduction](firmware/XDF_DEFINITIONS.md) retain the exact scope; this is representative integration coverage, not a native inspection of every map.

## Software work still possible with the existing files

| Priority | Work | Completion criterion |
|---|---|---|
| 1 | Later transient lifecycle | Join sampling, filtering, phase capture, curve selection, eligibility and injector timer events; replay stops/restarts, inhibits and interrupt overlap. The new pulse-calculation test covers only part of that chain. |
| 2 | Residual calibration coverage | Trace indirect references and copied configuration; review 884 early-family and 1,267 later-family bytes outside known map/header/axis layouts. Identify scalars, unused/conditional structures and further maps only with evidence. |
| 3 | Scalar catalogue reconciliation | Move already established settings from narrative/test findings into typed, image-specific definitions with byte ranges, dependencies and exact encodings. |
| 4 | Boot peripheral/recovery modelling | Desktop transport and serial-peer tests are implemented. Extend instruction-level flash-controller/watchdog modelling and interruption/recovery evidence; host-side simulation does not establish physical recovery. No destructive retries are enabled. |

## Work requiring physical or additional reference evidence

- Fitted MCU/package identity and actual oscillator/timer frequency.
- CPS geometry and edge angle against mechanical TDC, plus actual coil firing polarity/edge.
- Sensor bias/conditioning and absolute coolant, intake temperature, pressure and throttle-angle transfer.
- Connector face convention, OEM cavity numbering and measured board/transceiver continuity for the relevant ECU.
- Repeatable bench connection, independent matching readouts, recoverable flash trials and exact readback after writing.

These are specific missing observations, not reasons to stop the software work. Raw bytes and integer behaviour can be verified without pretending an unknown physical reference has been measured.

## Reproduction

The command list in [regression.yml](../.github/workflows/regression.yml) can be run locally; it is not triggered by a Pages push. Native-model fixtures additionally accept the compiled library path: `test_full_lift.py`, `test_control_semantics.py`, `test_extended_maps.py`, `test_map_consumers.py`, `test_map_selectors.py`, `test_crank_reference.py`, `test_connector_paths.py`, `test_spark_schedule.py`, `test_sensor_variants.py`, `test_units_variants.py` and `test_pressure_state.py` under `scripts/`. Build the library as described in the [full decompilation guide](full/README.md). The optional executable verifier requires the local YamahaFlasher path explicitly.
