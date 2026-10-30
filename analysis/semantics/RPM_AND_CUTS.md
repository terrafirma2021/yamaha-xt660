# Engine speed, spark cut and fuel cut

The [unit-decoding pass](UNIT_DECODING.md) now derives conditional RPM scaling using the service-correlated nominal clock and explicit crank-pattern assumption. Those assumptions are carried with the converted axes.

**Established:** raw speed calculation, three separate period-based cut flags, separate road-speed flags, and their output consumers. **Not established:** a verified RPM conversion or every reason for disabling ignition/injection. [Instruction evidence](rpm_cuts_evidence.txt) is authoritative for comparisons.

## Engine-speed variables

The timer-input routine `0xD871` reads capture register `0x0052`. It maintains timed interval state; selected intervals are stored into `0x0A38, 0x0A3A, …, 0x0A42` (six words). `0x73A5` sums these with unsigned saturation into `0x0A44`. Call this **P**, a period-domain quantity. Higher speed means smaller P.

At `0x73F7–0x741E`, integer/fractional division computes a reciprocal. For the tested non-overflow range `1200 <= P <= 65535`, the exact result is:

`speed_raw = min(0xFE00, 8 × floor(37500 × 256 / P))`.

This is stored in `0x08F8`. The factor of eight is applied after truncating the Q8 quotient, so values are multiples of eight. The invalid/stale-state path at `0x73A9` can instead supply `0x01E0`; do not interpret every value as a fresh measurement. Division-by-zero/overflow behavior outside the tested domain is not an RPM calibration rule.

`0x0906` is a second reciprocal estimate, based on the three-byte interval quantity at `0x0A4B–0x0A4D` shifted right twice into `0x0A80`. The history producer and its relationship to P are now traced and replayed below. `0x87E7–0x8824` averages and filters `0x08F8` into `0x08FE`.

ROM `0x18D7` selects downstream speed sources:

| Selector | RAM `0x0900` | RAM `0x0902` |
|---|---|---|
| Zero | `0x08F8` | `0x08FE` |
| Nonzero; stock is 1 | `0x0906` | `0x0906` |

The major quantity-map speed axes use `0x0900`; the main timing-map speed axis uses `0x0902`. A definition must distinguish measured period, instantaneous speed, filtered speed and selected speed.

### Stock speed-history path, checked across all nine BINs

The source selector is **1 in every registered BIN**. The ordinary map axes therefore use the history-based reciprocal. This is not a different unit convention from the six-pitch reciprocal, but its response to changing speed is different.

| Operation | Early application | Later application |
|---|---|---|
| History producer | `EB0B–EBC5` | `DFFE–E0B8` |
| Incoming capture interval, extended high byte / low word | `C07 / C08` | `C29 / C2A` |
| History count / ring index | `A52 / A53` | `A5C / A5D` |
| 22-word interval ring | `A54–A7F` | `A5E–A89` |
| 24-bit running sum | `A4F–A51` | `A59–A5B` |
| Published 24-bit history | `A4B–A4D` | `A55–A57` |
| History divided by four, saturated to a word | `A80` | `A8A` |
| History reciprocal | `0906` | `0926` |
| Source selector in ROM | `18D7` | `18B2` |
| Fuel / ignition speed coordinates | `0900 / 0902` | `0920 / 0922` |
| Telemetry divisor / output byte | `4E34 / AE2` | `45D2 / B05` |

The producer increments a saturating sample counter and skips its first event. It inserts each subsequent interval into a 22-entry ring, limiting an interval to 65535 if its extended high byte is nonzero. While fewer than 22 samples are stored, the published history is `22 * floor(sum / sample_count)`. After the ring fills, it is the exact sum of the latest 22 stored intervals. Ring replacement and sum arithmetic use a 24-bit total.

For published history H, the speed routine computes:

```text
P_history = min(65535, floor(H / 4))
speed_history = min(65024, 8 * floor(9600000 / P_history))
```

The reciprocal expression above is verified in the non-overflow input domain `1200 <= P_history <= 65535`. It does not define the CPU's divide/shift behavior for arbitrary smaller or zero periods.

On the documented ten-short/one-double capture pattern at constant speed, 22 captures contain **24 normalized pitch durations**. If one ordinary pitch takes t timer ticks, the full history is `24*t`, and the shift produces `P_history = 6*t`. The instantaneous path also sums six normalized pitches. Thus both reciprocals have the same steady-state scale. On acceleration/deceleration, their different windows must be preserved; a current period cannot be substituted for the rolling history.

At selector zero the fuel coordinate and telemetry use instantaneous speed, while the ignition coordinate uses the separate filtered speed. At every nonzero selector value both map coordinates and telemetry use the history reciprocal. All nine supplied images store telemetry divisor **190**:

```text
payload = min(255, floor(selected_speed / max(ROM_divisor, 1)))
```

The stale-state branch supplies 480 to the short-period speed path; it does not by itself replace the separately computed history reciprocal. The complete reset/ISR scheduling determines when history is retained or reinitialized, so a stale-state test is not a universal description of fault behavior.

[The replay test](../../scripts/test_speed_sources.py) checks every executed instruction against each BIN and compares the original p-code execution with independent history, reciprocal and spark-planner models. [The report](../firmware/speed_source_validation.json) records **28,602 checks across all nine BINs**: history warmup/ring replacement/count saturation, extended-interval saturation, steady and changing speeds, source selectors, payloads, stale short-period states, and all 256 final spark codes per image. These are selected software-path tests, not whole-ECU or hardware execution.

### Physical RPM convention and its evidence

ROM axis values are internally consistent with a reciprocal speed scale, but internal consistency does not prove revolutions per minute. To get physical RPM from P, establish the timer tick frequency `f_tick` and the number of crank revolutions `R` represented by P:

`RPM = 60 × f_tick × R / P`.

The program sets `0x004D = 5`, selecting bus/32 under the MCU peripheral model. Although the original dump has no boot, the [matching companion now provides a populated boot](LOCAL_XDF_REVIEW.md) with `SYNR=7`, `REFDV=1` and PLL selection: bus frequency is four times oscillator frequency. This resolves the boot arithmetic; it does not encode the oscillator's frequency in hertz.

The [service-tool rate and fan-diagnostic cadence](UNIT_DECODING.md) independently support the intended 500 kHz timer profile. With that profile and one twelve-pitch pattern per crank revolution, both map speed sources use **code / 5.12 RPM**, and the main limiter uses **15000000 / P RPM**. The map reciprocal quantizes down to multiples of eight; the limiter compares its own period directly. This is a derived nominal profile, not a measured clock or a separate proof of the physical rotor geometry. Plausible axis endpoints alone do not establish absolute units.

## Main period limits: three pairs

`0x7588–0x75C6` independently updates three bits in RAM `0x088C` using P. Every parameter below is an **unsigned, big-endian 16-bit ROM word**.

| Output gate | Resume parameter | Cut parameter | RAM flag | Confirmed consumer |
|---|---|---|---|---|
| Primary injector | `0x4BC8 = 2055` | `0x4BCA = 2054` | `0x088C:0x08` | `0xF519` exits before timer-6 scheduling |
| Spark | `0x4BCC = 2055` | `0x4BCE = 2054` | `0x088C:0x02` | `0x5664`, `0xEE78` and other timer-3 scheduling gates |
| Secondary injector-like path | `0x4BD0 = 2055` | `0x4BD2 = 2054` | `0x088C:0x04` | `0xF592` exits before timer-7 scheduling |

For each pair: **set cut when P <= cut value; clear cut when P >= resume value; otherwise preserve state**. Equality is intentionally different from the normal fan thresholds. Smaller period limits permit greater speed, assuming an unchanged clock and period definition. The stock period boundaries are adjacent integers, so there is no integer P strictly between them.

The secondary output code exists but `0xF592` returns immediately when variant RAM `0x0D87 == 9`, the stock value copied from ROM `0x18D3`. Its presence does not prove that this ECU has a second connected injector. Do not expose it as an active second-cylinder setting.

The fixture exercises all 65,536 period values with all three cut bits initially clear and initially set; each bit's decision is independent. These tests check flag behavior, not an engine's physical rev limit.

## Additional period limits under a separate condition

At `0x77C6`, RAM `0x08B1:0x08` decides whether another pair of injector cut flags is evaluated. If that bit is clear, `0x0886:0x04` and `0x0886:0x02` are cleared. If set:

| Output | Resume above | Cut at or below | Cut flag | Consumer |
|---|---|---|---|---|
| Primary injector | `0x34A8 = 1595` | `0x34AA = 1578` | `0x0886:0x04` | `0xF4E0` skips primary call |
| Secondary path | `0x34AC = 1595` | `0x34AE = 1578` | `0x0886:0x02` | `0xF4FC` skips secondary call |

Here the resume comparison is **strictly greater**, unlike the main period limits. The initiating fault/state's physical meaning is unresolved. Label these conditional period limits, not a proven limp-home rev limit.

## Road-speed cuts are separate

Timer-channel-2 routine `0xF3F3` increments counter `0x0AB0`. One consumer feeds diagnostic 07; another takes pulse-count differences, applies gain at `0x4BD4` and filter factor `0x4BD6`, and produces filtered road-speed byte `0x0ABE` at `0x9C69`. Neither km/h nor mph has been established.

Routine `0x6259` evaluates three byte-sized hysteresis pairs:

| Gate | Clear-below parameter | Set-at-or-above parameter | RAM flag |
|---|---|---|---|
| Primary injector | `0x4BDF` | `0x4BE0` | `0x089A:0x08` |
| Spark | `0x4BE1` | `0x4BE2` | `0x089A:0x02` |
| Secondary injector | `0x4BE3` | `0x4BE4` | `0x089A:0x04` |

The upper comparison is evaluated first. Between bounds the previous bit is kept. Exact stock bytes are in [catalog.json](catalog.json). These flags are independently checked beside the period flags in `0xF519`, `0xF592`, and `0x5664`. Changing an engine-period threshold alone does not eliminate these gates.

## Fuel-cut gate inventory

At `0xF49F–0xF4DF`, the normal injection dispatcher can return before either channel when any of these gates inhibits it:

- `0x088C:0x20`, `0x08A0:0x04`, `0x08B2:0x80`, `0x088C:0x80`, `0x0D08:0x01`, any bit of `0x0884:0x07`, `0x0885:0x40`, or `0x0BF8:0x80` is set;
- `0x08B0:0x08` is set while configuration `0x0DD9 != 0x80`;
- `0x08B1:0x10` is set;
- any bit in `0x0886:0xC1` is set.

After passing those gates, channel-event selection and conditional period bits control calls to `0xF519`/`0xF592`. Each entry adds its main period flag, road-speed flag and `0x08B1:0x80` check. Other asynchronous injection routines exist, including `0xC8C9` and `0xC939`; this inventory is the normal dispatcher, not proof that every possible pulse path has been exhausted.

The wide collection of conditions is why “fuel cut” must not become a single generic toggle. Deceleration, fault, interlock and synchronization interpretations must be assigned by tracing each flag's writers. The main period and road-speed bits are identified; many other physical reasons are still open.

## Spark suppression is likewise layered

Timer-3 scheduling has the main period and road-speed gates and additional engine-state/interlock checks. Some paths suppress scheduling; others terminate or change an existing timer event. A return before a new pulse is not automatically an immediate cancellation of a pulse already armed in hardware. The read-only tests stop at instruction boundaries and do not simulate timer execution.

Before exposing “spark cut” as an editor option, finish the producer/consumer audit for each relevant bit, distinguish new-event suppression from active-event shutdown, and verify the behavior under the selected operating state.
