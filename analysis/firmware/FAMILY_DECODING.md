# Application decoding across all nine BIN records

All nine registered images now have an instruction-byte-checked application-family assignment, their own extracted calibration values, and an image-specific map catalogue. This is **static decoding**, not a claim that every physical unit, function purpose, constant or hardware path is resolved.

## Two code families, separate calibrations

| Family | Images | Application entry | Instructions | Instruction bytes | Decompiled functions | Maps per image | Cells per image |
|---|---|---|---:|---:|---:|---:|---:|
| Early | Original 2005, corrected copy, 2004–06 companion, both 2C1-00 files | `0x5000` | 15,942 | 42,849 | 225 | 71 | 8,275 |
| Later | 5VK-1X, 5VK-11, both 2C1-10 files | `0x4800` | 15,928 | 43,134 | 229 | 77 | 6,938 |

The entire code span and application dispatch span match within each family, including embedded code-region data. Every exported instruction is also compared individually with every member BIN. Thus the existing early disassembly applies to both 2C1-00 files **without copying the original calibration values**. The later disassembly is shared by four images for the same byte-backed reason.

The count of 663 image-specific map records contains repeated layouts across related images; it is not 663 unique map designs. All 69,127 cell values are read from their own image. A map is not treated as physically scaled merely because its layout was recovered.

## What changed between the applications

- The early application has three 45 × 30 word fuel surfaces. The later application has two, at `0x1B40` and `0x2662`, selected through load and throttle processing. The original third surface is not inserted into the later catalogue.
- Later base ignition surfaces are at `0x38D2`, `0x3B52` and `0x3DD2`, each 32 × 20 bytes. Calls at `0x7C66` consume the selected surface; neutral and ratio-selection tests immediately precede that call. Absolute BTDC still requires the crank reference.
- Several transient corrections change from uniform-axis curves to explicit stored axes. Their later shapes come from the axis-index calls and the subsequent lookup arguments, rather than old addresses or XDF labels.
- Four coolant-indexed word curves at `0x446A`, `0x448C`, `0x44AE` and `0x44D0` each have 11 points. They supply a crank-synchronous PWM state machine that is disabled by the stored configuration in all four later BINs. The separate 12 × 12 surface at `0x451C` supplies a position-feedback controller. Their software roles are detailed below; the attached devices and physical scales remain unverified.
- The later coolant table is at `0x4713` and intake-temperature table at `0x46F2`. The ADC-coordinate transforms retain the familiar 29- and 33-point shapes. The later code also multiplies the internal temperature byte by 160 and takes the high byte (`0x69C7` and `0x6901`), then caps that result below 150. This proves a digital factor of 160/256 in that path; it does not independently prove a Celsius offset or analog circuit.
- Later initialization copies three lookup blocks from ROM into RAM: `0x185A → 0x0E32` (27 bytes), `0x32C9 → 0x0DA1` (18 bytes), and `0x32DB → 0x0DB3` (18 bytes). These maps are included; subsequent calls through RAM are linked to the ROM sources. A runtime write can still change those copies.

## Differences that matter within a family

The two 2C1-00 images change ten recovered map bodies relative to the original 2005 image: the normal load and throttle fuel surfaces, startup fuel, one post-start enrichment state, and six transient curves. Their application instructions remain identical. The two 2C1-10 images change nine recovered map bodies relative to the supplied 5VK-1X image: both base-fuel surfaces, startup fuel, and six transient curves.

The 5VK-1X and 5VK-11 images have identical recovered map bodies. Their four differing bytes remain separate evidence: a scalar at `0x348D`, the embedded identifier, and metadata/checksum bytes. `0x348D` is read at `0x5033`; it is outside the preceding extracted curve. Calling the files interchangeable or factory stock would go beyond this result.

The labelled immobilizer-off pairs have their own image records and unchanged source bytes. Modification labels are not a hardware behavior test. The later `0x4619` byte is copied into RAM `0x0E4D` at `0x58DF`; the second changed byte `0x4751` is retained in the residual-constant inventory, rather than silently classified as a map cell.

## Five later control maps: traced roles and operating modes

The [auxiliary-control replay report](late_auxiliary_validation.json) checks all four later images against independent integer expectations. Each executed instruction is compared with that image's original bytes. Tests use isolated RAM fixtures, including synthetic table values where the original flat surface would hide indexing mistakes. No source BIN is changed and no physical ECU is exercised.

| Map data | Software role | Lookup output | Consumer |
|---|---|---|---|
| `0x446A` | Initial PWM demand | `0x0AB2` | Copied to current demand `0x0ABA` and retained initial demand `0x0AC8` |
| `0x448C` | PWM hold demand | `0x0AB4` | Ends rundown; supplies the hold state |
| `0x44AE` | PWM rundown step | `0x0AB6` | Copied to `0x0AC0` on state entry and subtracted on qualified crank events |
| `0x44D0` | Suspended-demand decay step | `0x0AB8` | Subtracted from retained demand `0x0ABE`, which uses ten times the ordinary demand scale |
| `0x451C` | Position-feedback target vs speed and relative throttle | `0x0D5C` | Target selector, deadbands, ADC7 feedback comparison and paired PORTB bits 6/7 |

### Coolant curves and the disabled PWM path

The four word curves use internal coolant code `0x0914`. Their block at `0x6A5D`, state machine at `0xE40C`, output update at `0xE536`, and PWM initialization require configuration `0x1841` / RAM `0x0E55` to equal `0x40`. **Every supplied later image stores `0x80` at `0x1841`.** The tests establish the dormant code's behavior by changing only the test's RAM fixture; the BIN configuration is preserved.

State byte `0x0AB0` moves through delay (`0x80`), initialization (`0x40`), rundown (`0x20`), hold (`0x10`) and output-suspended (`0x08`) states. Internal speed thresholds copied from `0x445A` and `0x445C` provide hysteresis for suspension and resumption. When entering suspension from rundown, the retained demand is multiplied by ten with saturation; returning to rundown divides it by ten. Entering suspension from hold clears that retained demand. Delay saturation, state-entry blocking, both speed boundaries and these transitions are replayed.

Qualified crank events subtract the whole step in the 24-event path or `floor(step / 2)` in the 12-event path, clamping at zero. The initial event reloads retained initial demand. The hold path reloads the hold curve. `0xF050` applies the minimum-nonzero and upper-demand thresholds, with nominal full demand 1000, then converts the complementary demand into a crank-event offset and fractional delay. It wraps the event index and avoids the missing-event positions. `0xF12B` converts the fractional remainder using the captured period and writes the PWM duty-register pair at `0x00BC` / `0x00BD`. These are internal scheduling/count relationships, not established physical actuator units.

There is also a reproducible arithmetic caveat in byte-axis helper `0xC122`: it writes only the high byte of divisor scratch word `0x0E62–0x0E63`. The previous `0x0E63` value therefore affects fractional indices. For an interval width `d`, input distance `x` and old low byte `s`, the fraction comes from rounding `floor(x × 65536 × 256 / (d × 256 + s))` to an 8-bit fraction. The report checks all 256 coolant input codes with `s = 0, 127, 255`. This is preserved original instruction behavior; it is not silently replaced with ideal interpolation, and its actual runtime scratch history is not asserted here.

### Position-feedback target and overrides

The surface at `0x451C` uses selected speed `0x0920` and filtered relative-throttle code `0x08F0`; the latter follows subtraction of the learned closed-throttle reference at `0x80A7` and filtering through `0x80FC`. These axes remain internal codes. **All 144 cells are 55 in each supplied later BIN.** Flat values do not make the surface an unused placeholder: lookup results flow into the target selector at `0x93DE`.

The selector gives priority to a fixed target (`0x44E8 == 0x80`), startup target until the feedback reaches its narrow band, and the stopped-state target (`0x0881:20`). It can then hold the previous target, substitute recovery target `0x0AD8`, or accept the map result. Tests use distinct synthetic target values to prove each route despite the identical stored fallback values. The recovery ramp at `0x8EE9` increments a saturating timer, adds the configured step to a saturating accumulator when due, adds one of two base targets, and caps the result at the current map target. Reaching that cap clears the recovery flag and accumulator. Both base selections, timer boundaries, saturation and release are replayed. The subsequent [mode-trigger report](late_mode_validation.json) covers the complete upstream mode-state block, startup release and output-inhibit logic described below.

`0x96EA` builds saturated target bands of ±1 and ±7 using `0x45AC` and `0x45AD`. `0xAED0` compares ADC7 feedback `0x08E4` with those bands. Outside the narrow band, paired PORTB bits 6/7 select opposite output states; an inhibit flag or an in-band result selects both bits high. Wider-band entry and the cadence routine at `0xAFD3` control pulsing. Replay checks every 8-bit feedback value at six targets, direction changes, inhibition, both pulse-mask values, counter wrap and pulse-width saturation. Lower PORTB bits must remain intact.

### Shared mode entry, hold and recovery

The entire block `0x8CF6–0x8FAD` is now checked against an independent state model, including boundaries and multi-call sequences. It belongs to the scheduled `0x7E9E` task; the decompiler's `candidate_unreferenced_8b55` label does not make the fall-through code unreachable. The inputs are filtered road-speed code `0x0AEE`, ratio classifier `0x089A`, and the high byte of filtered throttle coordinate `0x08F2`. This last input is distinct from the relative-throttle coordinate `0x08F0` used by the position map.

Stored settings are identical across the four later images:

| Phase | Condition / action |
|---|---|
| Qualification | Road-speed code is strictly between 43 and 52. Outside that window, an armed qualification is reset. Ratio class 3 must persist for 100 counting ticks. The alternative lane is configured for class 255; the normal classifier produces only 0–5. |
| Trigger | Throttle code reaches 61 after qualification. The position target is held during qualification/confirmation. |
| Confirmation | Throttle must reach 154 before 20 counting ticks expire. Timeout cancels the request. |
| Active | Select ignition code 75, fuel-gain code 0 and position target 55. Exit when throttle falls below 154 or 130 counting ticks expire. |
| Ignition recovery | Add one code every six service calls until reaching the current base-map code, then release the override. |
| Position recovery | Add four codes every five service calls, capped by the current position-map target. Here the starting and final targets are both 55, so release occurs at the first due update without changing the target. |
| Fuel recovery | Move the gain toward neutral code 128 by ten codes every six service calls. This state arithmetic remains present even though the supplied extra-fuel-gain consumer is disabled. |

The speed-window bit does not continuously gate an already-active correction: loss of the window is handled through the qualification state. The tests preserve that distinction. Ratio class is a software classification, not a proven numbered gearbox gear. Road-speed and throttle thresholds above remain codes, not an asserted km/h or throttle-degree calibration.

ROM `0x4123 = 0x80` enables the normal-ignition override at `0x7DA7`. ROM `0x4124 = 0xFF` disables the corresponding extra fuel multiplier. In a complete replay with base ignition code 115, ignition moves to 75, then recovers through 76…115; the selected position stays 55 throughout. Synthetic alternate-lane constants separately prove the position ramp can produce `31, 35, 39, 43, 47, 51, 55` when its starting target differs. This separates real stored behavior from merely present capabilities.

The service divider is 2,500 timer ticks. Qualification/confirmation/active counters advance on every second service call; recovery counters advance on each call. Under the project's independently documented **nominal 500 kHz timer profile**, those correspond to 5 ms service calls and 10 ms counting ticks: 1 s qualification, a 200 ms confirmation window and a 1.3 s maximum active interval. These are nominal software timings, not measurements on an ECU.

### Startup, stopped-state selection and output protection

Initialization at `0x5F95` selects the startup target and sets `0x0D59:04`, unless fixed-target mode is selected. The latch clears only after the feedback reaches the narrow target band. The stopped-state flag `0x0881:20` is set at startup and in the missing-crank timeout path `0x60A8`; the valid-crank branch at `0xD814–0xD85E` clears it. Both the startup/feedback handoff and valid-crank release are replayed.

The previously unexplained inhibit bit `0x0D59:20` comes from `0xA837–0xA8BD`. After 50 unchanged-direction service samples it inhibits drive. The first attempt pauses for 25 samples; a subsequent attempt uses 100 periods of 25 samples before retry. Reaching the narrow target band or changing direction resets the controller's counters/phase as shown by the feedback routine. This timeout task runs every eighth main service tick: nominally 40 ms per sample, giving 2 s before inhibition, a 1 s first pause and a 100 s later pause. These are the stored controller rules, not evidence that a motor is physically fitted.

### Resolved internal/electrical scales and the hardware boundary

The PWM demand has full scale **1000**, so its internal scheduling-window fraction is `demand / 1000`; a demand count represents 0.1% of that window. The suspended accumulator has ten times that scale, so its decrement count represents 0.01%. Clamping, event quantization and the 12-event path's halved decrement still apply. These fractions do not establish valve opening, airflow or mechanical travel. PWM initialization selects concatenated channels 0/1 and enables channel 1, whose conditional MCU-reference output is **PP1**.

The position target's scale is also resolved electrically: normal conversion uses a left-aligned 10-bit ADC result, and `0x6B29` retains only its high byte. Thus `feedback = floor(ADC10 / 4)`. Target 55 represents codes **220–223**; its ±1 band accepts **216–227**, and its ±7 band accepts **192–251**. All 1,024 possible conversion codes are checked through feedback and startup-target release. A voltage conversion additionally requires the actual reference voltages; a mechanical angle additionally requires the sensor transfer and linkage. Neither is a constant that can be recovered from this comparison alone.

The existing conditional [NXP MC9S12T64 reference](https://www.nxp.com/docs/en/data-sheet/9S12T64AF16V1.pdf), PDF pages 60, 94–97 and 264–265, places PB6/PB7 at package positions 26/27, ADC7 at 66 and PP1 at 13. These are MCU-reference signals, **not measured ECU connector pins**. The [Yamaha 2007 R/X supplement](https://www.motomatrix.co.uk/yamaha-pdf/XT660X-R2007_Suppl_manual.pdf), PDF pages 54–55, 79 and 81, shows the injection circuits and a fast-idle plunger, but no matching paired-output position servo. That supports checking for unused shared-platform circuitry; it does not prove this board lacks a driver or establish the 2C1 board routing. No EXUP/idle/throttle actuator identity is assigned by elimination.

The remaining hardware evidence is specific: identify the fitted MCU/package, trace PB6/PB7 and ADC7 through the driver/conditioning circuitry to any connector, and identify the connected sensor/actuator and its calibration. This work requires the relevant board/schematic or measurements; the software trigger and code-scale questions above no longer depend on it.

## Code coverage and decompiler limits

The later application's only non-instruction spans before metadata are:

| Range | Meaning |
|---|---|
| `0x61B6–0x61D5` | ADC handler pointer table, reached through indexed dispatch |
| `0xBC32–0xBC43` | Reciprocal/shift lookup constants, referenced at `0x773B` |
| `0xB0EC–0xB5FF` | Uniform FF padding |
| `0xF577–0xF76F` | Uniform FF padding |

Flow roots include the entry/interrupt dispatch, indirect ADC entries, unique original-function prefix candidates, and explicitly marked unreferenced candidates. A structurally decoded candidate does not prove execution or an original source-level function boundary. Pseudocode retains warnings about stack changes and infinite loops. All 229 recovered later functions decompile; the application-only program deliberately leaves boot target `0xF8A0` external. The five populated boot images share the separately decoded [boot region](xt660-2004-2006-companion/BOOT.md). Four FF-filled boot regions remain absent, not reconstructed reads.

## Artifacts and verification

The subsequent [pressure/load pass](../semantics/PRESSURE_ESTIMATE.md) and [normal fuel-transfer pass](../semantics/MAP_CONSUMERS.md#fuel-transfer-checked-in-both-firmware-families) add instruction replay across all nine BINs. They verify family-specific sampling/fallback behaviour, the estimator's complete acceptance gates, both load-normalization paths, normal fuel gains and primary request construction. In particular, the later family does not retain the early alternate pressure-estimator selector, second normal coolant lane, or early reduction at the blend-to-limit stage. These are code differences, not interchangeable labels.

- [Later structured pseudocode](families/late/decompiled.c), [disassembly](families/late/disassembly.tsv), [function index](families/late/functions.tsv), [references](families/late/references.tsv), and [compressed instruction p-code](families/late/full/instructions.jsonl.gz).
- [Early structured pseudocode](../decompiled.c) and [complete early instruction translation](../full/README.md).
- [Family verification](family_verification.json), [per-image catalogue](decode_catalog.json), and [lookup execution results](lookup_validation.json).
- Each image directory contains `maps.json` and `decode_review.json`. These include cells, stored axes, caller evidence, changed-map summaries, every explicit calibration operand, and remaining calibration byte ranges.

The lookup tests execute each image's actual CPU12 p-code against its cells at selected knots, clamp/fraction points and inline threshold boundaries. Synthetic step-table values check indexing even where the stored table is constant. These tests exercise recovered lookup arithmetic; they are not complete application simulations, physical CPU validation or engine tests.

Run `decode_firmware_maps.py --check`, `audit_firmware_families.py --check`, `test_firmware_lookups.py`, `test_late_auxiliary_controls.py --check`, `test_late_mode_triggers.py --check`, and the website validators. `run_family_analysis.ps1` rebuilds the later disassembly using the repository CPU12 processor and recorded seeds. The site shows separate grids for each BIN and retains model-specific wiring boundaries.

## Still open

The early calibration region has 884 bytes outside the map/header/axis catalogue; the later region has 1,459. Those ranges include constants, flags and potentially unidentified structures, and are preserved in each image's review. Every explicit code reference to them is indexed, but not every meaning is assigned. Several later table names intentionally describe their input or output rather than guessing an actuator.

No new claim of complete physical scaling is made. Sensor circuitry, final spark reference, fitted MCU/package identity and exact bike/market/ECU matching remain separate evidence requirements. There is no verified tuning export or live-flashing approval implied by this decoding.
