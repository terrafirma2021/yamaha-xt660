# Map consumers across operating sequences

This pass joins the previously isolated calculations to state transitions and output-register writes. It adds **31,937 operating-sequence fixtures** and **14,260 pressure interleaving fixtures**. Every executed instruction is compared with the corresponding registered BIN. Original firmware files are unchanged.

| Evidence scope | Images | New checks |
|---|---:|---|
| Post-start initialization, reset/reload and repeated decay | All nine | Nested gates, coolant changes, reload enabled/disabled, 80 successive updates per lifecycle |
| Transient fuel, phase limiting, injection dispatch and alternate ignition | Five early-family images | Trigger/rearm branches, actual map lookups, pulse combination, timer writes, event counts and coil scheduling |
| Pressure acquisition interrupted during task calculations | All nine | One actual producer invocation at each instruction boundary in the chosen consumers |
| Early alternate pressure estimator | Five early-family images | Sample update before/after the consumer's word load, target tracking |

The two reports preserve individual image hashes, executed instruction addresses, test/dependency hashes and scope limits: [operating sequences](../firmware/operating_sequence_validation.json), [pressure interleavings](../firmware/pressure_interleaving_validation.json). Later transient/ignition paths are not certified by an early-family fixture. Neither report is an ECU bench certificate or an exhaustive full-firmware state-space proof.

## Post-start enrichment lifecycle

Early initialization at `715A–7190` is nested: `883:20` must be clear to enter at all, then `884:08` must be clear to load the two states. Their values are the **Q8 lookup results**, including interpolation fractions, from `curve_32ef` and `curve_3301`. A coolant change on the next call does not reload them while the outer flag remains set.

Reset routine `721F` clears `883:20`, but leaves `884:08` unchanged. At `7381`, `ROM[32EE] != 128` independently reloads both states from current coolant. Therefore clearing only the outer flag does not guarantee another initialization, and disabling reset reload does not erase the existing enrichment.

Every fuel update at `7FD8–800C` applies:

```text
state_A = 2 * max(0, floor(state_A / 2) - ROM[3313])
state_B = 2 * max(0, floor(state_B / 2) - ROM[3314])
combined = max(state_A, state_B)
```

The low bit is discarded even with a zero decay byte. These are two decaying states selected by maximum, not a sum of two independent enrichments. Existing consumer tests cover every 16-bit decay state; this new fixture links initialization, reset and repeated decay.

The later family uses the same nested flags at `69E8–6A1E`, with states `992/994`, maximum `990`, and decay at `765A–768E`. Its two curve headers/cells are copied from `32C9–32EC` to RAM `DA1–DC4`; reset routine `F3A8` uses RAM selector `DA0`. The fixture supplies those exact copied bytes rather than reading the early addresses in a later BIN.

## Transient fuel: two different delivery mechanisms

The early speed-dependent threshold at `3494` compares against capped filtered TPS, maintaining the `B18/B19` qualification counters. It is not itself an injector duration. Six history-response curves select neutral, ordinary ratio and extended ratio paths separately for the following two mechanisms. Their input remains the clipped TPS position change described in [input coordinates](INPUT_COORDINATES.md).

### Immediate extra pulse

`91B6–93D7` qualifies speed, throttle, history change and operating state. It evaluates the actual pressure, IAT, response and throttle lookups, using the periodically evaluated coolant factor. The exact joint factor arithmetic produces `A0A` in timer ticks; an individual factor does not have a unique milliseconds conversion.

The pulse must exceed `ROM[34CC]`. Its sum with the auxiliary `A12` contribution is limited to **25,000 ticks**, then supply compensation is added with 16-bit saturation. The secondary request also applies the recovered secondary-channel multiplier. Output inhibits are checked before the actual `C8C9/C939` helpers are called.

Rearming uses more than a boolean:

- `B21 == 1` admits evaluation. Other values decrement and skip it; byte zero wraps to 255.
- After an accepted-size calculation, the code increases `B21` until the compensated request fits its count-dependent interval, or the counter reaches 27.
- `B20/B1C` impose a separate window/count limit. An expired window clears both counters and accepts a pulse, including when a synthetic within-window limit is zero.

The replay covers the three response selections, qualification boundaries, countdown states, window expiry, output inhibits, primary output and the non-9 secondary output. Immediate-pulse overlap fixtures cover both input pin levels, pending events, signed half-range decisions, timer wrap and the retained-duration subtraction. Some duration additions wrap at 16 bits; they are not silently changed to saturation in the model.

### Correction retained across counted injection events

`93DB–95A6` computes a separate correction (`D02/CFA`) and combines it with the normal primary/secondary quantity, calibration limits and supply compensation. Resulting requests are `CF6` and `CFC`.

`CF2:02` records trigger eligibility; `CF2:01` records an active episode; `CF2:04` is cooldown. Starting an episode additionally requires the cycle-identified flag `CA8:01`, no relevant inhibit, nonzero event limit `DA4`, and no active cooldown. The calculation can continue from retained active state after initial trigger eligibility is lost, subject to the later retention gates.

Actual injector output handlers increment `CF3` for active events. The final active event still uses the enriched request; reaching `DA4` then clears active state and optionally starts cooldown. Cooldown increments `CF4` until `DA5`. The fixture runs complete episodes of 1, 2, 5 and 255 counted events and subsequent cooldown, using actual output-handler instructions.

**The two channels share these event counters.** In the exercised non-9 path, alternating primary and secondary events advances one shared episode, not one independent counter per cylinder. This is an observed dormant code path, not evidence that a particular twin-cylinder ECU uses the supplied XT calibration.

## Injection phase, secondary channel and timer overlap

The modulo-24 map's clamped result feeds `EC98`, not directly a timer compare. With selector `D9B == 128`, old and requested phases are rotated around origin `D7E` and limited by step `D9C`. Gap codes receive direction-dependent substitutions: advancing through 11 selects 12, while the direct/decreasing path converts 11 to 10. The replay checks valid-domain origin, target, old-phase and step boundaries against an independent cyclic model.

The main consumer at `85A2–85BD` publishes the selected phase and delay to each channel. Dispatcher `F4E0` uses `C04` in ordinary mode and `923` in the phase-aligned mode selected by `88B:80`. The actual primary/secondary dispatchers, output helpers and edge handlers are exercised with immediate, delayed, overlapping and queued requests, including timer wrap. Variant **9** skips normal secondary dispatch at `F592`.

Two easily missed details are retained exactly:

- A primary dispatch accepted at `F519` clears `88C:30` before the secondary dispatcher examines its inhibits. Those gates cannot be modeled as independent snapshots.
- In the secondary special scheduling paths, active retained correction writes **primary request `92A`** at `C847` and `C897`; it does not write `92C` there. The fixture checks this cross-write. Its intended purpose is not established, and the binary is not changed to an assumed symmetrical implementation.

The physical phase of these event codes relative to the crank remains a separate reference problem. Arbitrary out-of-domain phase/configuration bytes are not approved tuning ranges.

## Early alternate ignition through coil scheduling

The periodic task evaluates `correction_surface_D` into alternate base `A88`, and `curve_4a33` into a TPS threshold `A89`. `9664–96F5` combines coolant hysteresis, normalized-period limits, a steady-history counter, throttle threshold, TPS faults and the variant-9 neutral requirement to set `885:20`.

Ordered tests cover entry, throttle exit, hot exit, hysteresis retention, cold re-entry, fault exit, neutral/variant differences, period extremes, delta reset and rearming. The selected base then passes through multiplier recovery and the real main-loop spark planner caller at `5416–5435`. Charge/fire dispatch runs at explicitly simulated capture edges and checks timer compare values and output-control bits. Normal firing opportunities preserve the requested dwell; the period and `88D:20` inhibit cases retain their real output behaviour.

This establishes the connection between the alternate maps and relative coil timing in the tested modes. It supplies neither a measured coil waveform nor an absolute BTDC offset.

## Pressure task/interrupt interaction

The early five-sample task at `869E` copies its history **one word at a time**, as does the later counterpart. The busy bit is not an atomic snapshot of the five-word window. Injecting one actual ADC-result publication before each consumer instruction produces six outcomes in the fixture: the original window, or one updated slot. No torn half-word is produced by these instruction-boundary tests.

The load filter similarly reads two source words separately. One producer invocation between those loads can yield these source pairs in the fixture:

```text
old first, old second
old first, new second
new first, new second
```

Each resulting filter calculation and normalized output is checked, including the interrupt's own instantaneous-load calculation. This is an explicit ordering result, not a claim that the pair is always coherent. The early alternate estimator takes one source word into its own retained target; preemption before or after that load selects the new or old complete value, respectively.

These tests preserve the interrupted CPU registers and use a separate producer stack. They execute the identified producer blocks, not ADC conversion latency, the whole interrupt entry/exit sequence or an unlimited interrupt stream. Physical interrupt timing and overrun behaviour still require the actual ECU.

## Physical references reviewed again

| Quantity | What the code establishes | Why an absolute value remains conditional |
|---|---|---|
| Timer ticks → time | Prescaler and divider arithmetic; nominal 500 kHz profile supported by service timing and communication-tool baud | PLL configuration specifies a frequency ratio. The fitted oscillator or a measured timed output is still missing. |
| Speed → RPM | Reciprocal calculation and normalized CPS pitch history | Mechanical pitches per crank revolution are not an independently measured rotor identification. |
| Ignition → BTDC; injection → crank phase | Event selection, relative compare times and state transitions | Rotating the trigger pattern relative to piston TDC leaves all interval arithmetic unchanged. The missing datum is the physical CPS/TDC relationship. |
| Coolant/IAT → °C | Complete digital lookup, replacement and diagnostic conversion | At fixed candidate slope, thirteen offsets from −36 to −24 fit the supplied resistance tolerances with different unmeasured pullups. Code cannot choose between those circuit explanations. |
| Load/pressure estimate → kPa | Sampling, replacement, normalization and signed filters | ADC/reference/conditioning transfer and the absolute-pressure scale are not established by an internal normalization constant. |
| Supply code → volts | ADC-derived code, filtering and replacement | The divider and ADC reference determine external volts per count. A plausible diagnostic scale is not a measured divider. |
| TPS → mechanical angle | Learned reference, relative counts, clipping and history | Position counts and the learned closed point do not establish the sensor's mechanical angular transfer. |

The [NXP specification](https://www.nxp.com/docs/en/data-sheet/9S12T64AF16V1.pdf) defines the MCU's clock and ADC relationships, not the ECU board's fitted oscillator or conditioning components. The Yamaha service manual's 9° BTDC at 1,400 rpm is a physical service specification; it does not identify which sampled edge corresponds to TDC in the dump. The existing [clock/source comparison](EXTERNAL_SCALE_CHECKS.md), [temperature counterexamples](TEMPERATURE_PROFILE.md), [crank reference](CRANK_REFERENCE.md) and [pressure trace](PRESSURE_ESTIMATE.md) retain the evidence and precise missing references.

Accordingly, affected map pages now distinguish the newly replayed software sequences from physical references and hardware validation. Conditional units remain conditional. No guessed unit or dormant-mode hardware identity has been promoted to verified, and no tuning/flash limit has been widened by these tests.

Reproduce:

```text
python scripts/test_operating_sequences.py --check
python scripts/test_pressure_interleaving.py --check
```
