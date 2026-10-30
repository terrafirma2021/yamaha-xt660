# Additional MCU pin findings — both firmware families

The early and later applications use the same **conditional MC9S12T64 80-pin package reference**. They are separate code families, not two independently identified MCU part numbers. This review checks all nine registered BINs against their own instruction bytes. The package marking and physical board routes remain unconfirmed.

## What the totals mean

| Images | Previously checked positions | Now checked | Runtime-use evidence | Configuration-only evidence |
|---|---:|---:|---:|---:|
| Four early images without captured boot | 35 | 53 | 38 | 15 |
| Early populated-boot companion | 37 | 56 | 40 | 16 |
| All four later images | 38 | 56 | 42 | 14 |

Runtime-use evidence establishes an instruction-level use, sometimes with an unresolved external purpose. **Configured** establishes a direction, initial latch or peripheral selection. Neither status means connector continuity has been measured. All 80 package labels have a separate datasheet transcription check.

The early images without boot are the owner dump, checksum-fixed derivative and the two 2C1-00 images. The companion and all four later images contain the recovered boot; only those five receive boot instruction checks for SCI0 RX/TX and PE1 interrupt disable.

## PA5 / PA6 / PA7: service-test selection

Package positions **52, 53 and 54** are inputs in both families: `DDRA=0x1F`. The application reads `PORTA & 0xE0`, then checks an additional RAM permission bit and repeats the port read before entering a test.

| Masked input | Action, when permitted | Early decision/target | Later decision/target |
|---|---|---|---|
| `0x80` | Full-range checksum test; call with end bound `0xFFFF` | `A2B9…A2E1` → `A489` | `951A…9542` → `971D` |
| `0x00` | Disable maskable interrupts and remain in an infinite loop | `A2E6…A2F9` | `9547…955A` |
| `0x40` | Destructive RAM test: `0x5555`, then `0xAAAA`, at even addresses `0800…0FFE`; terminal polling loop | `A2FB…A30C` → `A505` | `955C…956D` → `9799` |
| Other patterns | No service test entered | `A30F` | `9570` |

Permission is `08B1:80` early or `08B3:80` later. PA5 must be low for the three recognized patterns. These are application test selectors, separate from the MCU's reset-mode pins. A low or high external wire is not enough to establish the permission state. No test-point or connector route is assigned.

## Later PB5: an active gated output

Package position **25** was previously unassigned. Later startup writes `PORTB=0x1F`, `DDRB=0xEC`, making PB5 an output initially low. The gate at `A90B…A95E` sets it at `A956` or clears it at `A95B`.

For the high state, all these tests must pass:

- ROM `37E8 == 0x80`; this holds in all four registered later BINs.
- RAM `0881:10` is clear, and elapsed counter `09B6 >= 09B4`.
- `0CB2 <= 09B8`.
- Bits `08B1:20`, `08B1:10` and `08B2:80` are clear.
- High byte of `0C62` lies in `0x1A…0xF5`, and byte `08DC` in `0x07…0xF7`.

If either `08A3:04` or `08B4:80` is set, this block preserves the previous output instead of recalculating it. Reset handling at `C6AD` separately clears PB5. The tested masks preserve the other seven PORTB bits.

`09B4` comes from the coolant-indexed table with body `37EE` (pointer `37EB`); `09B6` is the saturating elapsed counter, reset while `0881:10` is set. `09B8` comes from the speed-indexed table with body `381C` (pointer `3807`, axis `380A`). These two tables therefore feed the **PB5 auxiliary-output gate**; their attached device remains unidentified. The manual's oxygen-heater circuit is a lead to compare against a board trace, not sufficient evidence to label PB5 as its driver.

Early PB5 has a different finding: it is initialized high as an output, with no dedicated subsequent bit operation found in the decoded application.

## Additional configuration recovered

| Package positions | Signal | Finding |
|---|---|---|
| 79 / 3 | PT0 / PT4 | `DDRT=D9`: outputs, initialized low / high. PT4 has `TIOS4=1` but compare action `OM4:OL4=00`; no TC0/TC4 direct access was found. |
| 17 | PP5 | Output initialized high in both families; no dedicated runtime write found. |
| 18 | PP6 | Early: output initialized high. Later: already traced to a conditional runtime output. |
| 22 / 23 | PB2 / PB3 | Outputs initialized high. Whole-port debounce copies do not establish switch inputs. |
| 25 / 26 | PB5 / PB6 | Early: outputs initialized high. Later: PB5 gate above; PB6 participates in the previously traced paired output. |
| 48 | PA3 | Output initialized high in both families; no dedicated runtime purpose established. |
| 46 | PA1 | Later: output initialized low. The early secondary-injector readback path is not present in the later application. |
| 74 | PS7 / SS | High GPIO output at startup. SPI master mode uses reset `MODFEN=0`, leaving SS outside SPI control; PP3 is the storage strobe. |
| 36 | PK7 | `DDRK=80` requests output where GPIO is available; no direct PORTK access identifies its purpose or latch value. |
| 41 / 44 | PE4 / PE7 | `DDRE=9F` requests output. PEAR/reset mode determines whether GPIO or an alternate function owns the pin. |
| 42 / 43 | PE5 / PE6 | `DDRE=9F` requests input; reset-mode and instruction-pipe functions remain distinct from GPIO configuration. |
| 38 | PE1 / IRQ | Recovered boot writes `IRQCR=0` at `F841`, disabling external IRQ requests. No application write re-enables it. Counted only where boot is present. |

Absence statements are scoped to the decoded code and reviewed direct register references. They do not establish that a pin is physically unconnected, safe to repurpose, or exposed at the ECU connector. No connector association was added by elimination.

## Remaining package-only positions

With a populated boot, the remaining **24** positions are 15 power/reference/regulator positions and nine special-function positions:

- **7–9:** BKGD and synchronous debug/programming interface. No application GPIO route or connector exposure is established.
- **28:** RESET. The startup low-voltage reset enable is visible in code; it does not reveal the external reset wiring.
- **29, 30, 32:** EXTAL, XTAL and XFC. The recovered boot configures the PLL (`F807…F81A`), but code does not establish the fitted crystal, filter components or board wiring.
- **37:** PE0/XIRQ. This is an input-only package function. No dedicated application use or external route was established.
- **78:** TEST. The datasheet requires grounding in normal applications; this is a hardware requirement, not proof of the actual board connection.

For the four early images without captured boot, positions **38, 67 and 68** also lack instruction verification in that exact image. The recovered companion's boot is shown as reference evidence only.

## Checks and datasheet references

`scripts/test_pin_configuration.py` executes **13,866 cases across all nine BINs**: startup register values, every 8-bit PORTA selector with permission set/clear, and boundary/random PB5 gate cases. Selector replay stops before destructive RAM tests, checksum subroutines and halt loops. Each executed instruction is compared with the selected BIN. Tests neither connect to an ECU nor alter firmware files.

The same script inventories direct configuration-register references and rejects unexpected changes to the reviewed setup. `scripts/test_pin_families.py` checks family separation, per-image boot applicability, evidence categories and byte provenance. Machine-readable results are in `analysis/firmware/pin_configuration_validation.json` and `analysis/firmware/pin_audit.json`.

Source: [NXP MC9S12T64 revision 1.1.1](https://www.nxp.com/docs/en/data-sheet/9S12T64AF16V1.pdf), PDF pages **60, 73–75, 86–90, 99–101, 147–155, 159–160, 175, 257, 261, 264–265, 385 and 463–464**. Direction values are interpreted alongside peripheral overrides; a DDR bit alone is not a complete mux configuration.
