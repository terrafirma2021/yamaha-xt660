# ECU pin audit across the registered BINs

The pin explorer now selects **instruction evidence for the actual BIN**, independently of map sharing. All nine registered images are checked. This repairs the missing explorer on later ECU pages and early companion pages; it does not certify a physical connector from a filename or calibration match.

Three different checks are shown separately: instruction bytes in the selected BIN, package positions against the MC9S12T64 datasheet, and physical ECU identification/board continuity. The first two are reproducible here. No supplied chip marking or PCB continuity record establishes the third. A software role can still be tentative even when its instruction bytes pass.

| Registered image | Application | Positions with code anchors checked | Boot |
|---|---|---:|---|
| XT660X 2005 / 5VK-8591A-00 | Early | 53 | FF placeholder |
| XT660X 2005 / checksum-corrected copy | Early | 53 | FF placeholder |
| 2004–2006 companion / 5VK-8591A-01 | Early | 56 | Populated |
| 2C1-8591A-00 | Early | 53 | FF placeholder |
| 2C1-8591A-00 / immobilizer-off | Early | 53 | FF placeholder |
| 2008 / 5VK-8591A-1X | Later | 56 | Populated |
| 2C1-8591A-10 | Later | 56 | Populated |
| 2C1-8591A-10 / immobilizer-off | Later | 56 | Populated |
| 5VK-8591A-11 | Later | 56 | Populated |

The [additional pin review](../semantics/PIN_CONFIGURATION_REVIEW.md) separates runtime use from configuration-only evidence. It adds the PA5/PA6/PA7 service-test selector, the later PB5 gate, idle output configurations and boot IRQ disable. Replays cover 13,866 cases across all nine BINs.

All 80 package position labels are compared with the reviewed manufacturer drawing. The code counts are not counts of physically verified ECU terminals. Source filenames, owner labels and parts-catalogue associations retain their existing evidence limits.

## Connector differences and the flashing sketch

The later review also recovered an independent **26-position ECU-face photograph** in the supplied XT tools folder. It marks upper positions 3 / 7 / 12 for power / ground / K-line and corroborates the horizontally reflected early manual reference. The new [flashing connector review](FLASH_CONNECTIONS.md) records both sources, their different housing widths and the remaining fitment/view limits. This does not transfer numbering from the later sketch to the early connector.

The [2004 Yamaha 5VK1-AE1 manual, PDF 462](https://scootertuub.nl/motoren/Yamaha/Yamaha%20XT%20660%20R%20X%202004%20Service%20Manual%20%20.pdf#page=462) draws **26 positions**: two rows of 13, with 23 wire labels and three crosses. The [2007 R/X supplement, PDF 81](https://www.motomatrix.co.uk/yamaha-pdf/XT660X-R2007_Suppl_manual.pdf#page=81) draws **34 positions**: two rows of 17, with 25 wire labels and nine crosses. Crosses do not prove whether physical metal contacts exist.

The later drawing adds **P, oxygen-sensor heater control**, and **Gy/G, oxygen-sensor signal**. Their paths were visually followed through the full circuit drawing. The sensor has separate R/W heater supply and Gy signal return. The signal function correlates with late ADC2/O2 feedback and fault 24; the heater's MCU command remains unresolved.

The supplied [XT660_PinOut.JPG](../../dataset/sources/xt%20660%20r/XT660_PinOut.JPG) is labelled 2C1-8591A-10 / XT660 2012 and has 34 positions. Its three coloured terminals correlate with the later manual after reflecting the drawing horizontally:

| Flashing-sketch number | Later manual research coordinate | Wire | Function |
|---|---|---|---|
| 3 | U15 | R | Power |
| 7 | U11 | B/W | Ground |
| 12 | U06 | Y/L | Communication |

This is a consistent orientation hypothesis, not independently verified Yamaha cavity numbering. Neither source states the view convention. **The sketch's 3 / 7 / 12 labels must not be copied onto the early 26-position drawing.** The manual itself does not bind every registered part-number label/market to this physical housing. Exact fitment remains separately qualified in the explorer.

The site uses U01… and L01… solely as left-to-right research coordinates in the selected manual. They are not MCU numbers or manufacturer cavity numbers.

## Application differences established from code

| Function | Early application | Later application | Later instruction / dispatch evidence |
|---|---|---|---|
| PAIR valve | PP1, package 13 | **PP0, package 12** | Normal control 91EF; diagnostic 48 A465/A487; DDRP FF at 482C/482E |
| PP1 | PAIR | Diagnostic/fault-pattern output; destination unresolved | A077/A080; diagnostic 54 A635/A653 |
| PT7 | Secondary injector timer path in the early study | Auxiliary GPIO output, diagnostic 49 | 6CC9/6CD2, A4C5/A4E7; no direct TC7 compare write found in the decoded later application |
| ADC7 | Skipped in ordinary scan | Sampled, stored at 08E4; external purpose unresolved | 61B6 dispatch, 616C scan selection, handler 6B29 |
| PE2/PE3 | Banked analog acquisition cycles | Initialized low; secondary dispatch tables point to RTS | 48A0/48A2/48A4 and 4B0E/4B10/4B12; 61C6/61CE point to 61F4 |
| PB6/PB7 | Early roles not portable | Paired PORTB output; destination unresolved | AF8D…AFCE; DDRB EC at 4824/4826 |
| PA1 | Early injector-path readback/control bit | Output initialized low; device unassigned | PORTA F8 / DDRA 1F at 4818…481E |
| PB5 | Output initialized high | Active conditional auxiliary output; device unassigned | A90B…A95E; set A956 / clear A95B |
| PA5/PA6/PA7 | Guarded service-test selector inputs | Same selector logic at later addresses | 951A…9570 → checksum 971D, RAM test 9799, halt 9558 |

The later ADC dispatch is checked directly at 61B6 in every later BIN: TPS, MAP, O2, intake temperature, supply monitor, lean angle, coolant, additional analog input. Diagnostic selectors are independently compared with the copied ROM list at 46C2 and their handler paths. GPIO direction writes, timer selection, and SCI/SPI setup are included in the evidence.

The early ADC2 role is now named oxygen feedback rather than left as an unspecified candidate. Existing [O2 tracing](../semantics/O2_CONTROL.md) establishes that software function; stock early variant 9 and zero eligibility maps leave feedback inactive. It does not create a missing O2 wire in the early harness drawing.

## Serial pins and flashing

Application communication uses **SCI1**, PS2/RxD1 and PS3/TxD1, conditional package pins 69/70. All nine application byte sets are checked. The recovered boot uses **SCI0**, PS0/RxD0 and PS1/TxD0, pins 67/68, with divisor 0068. Those boot instructions are present and checked in five images; the other four explicitly show **Boot not captured** instead of claiming successful verification.

The flashing-tool protocol establishes the boot command stream and 9,600 baud. It does not by itself show the transceiver/PCB path from the sketch's K-line terminal to SCI0, SCI1, or both. The Y/L manual circuit and dashboard/immobilizer behavior corroborate the application communication function. See [flash tooling](FLASH_TOOLING.md) for command evidence.

## Remaining physical and identity checks

- Read the actual MCU marking to confirm the conditional 80-pin package identification.
- Establish connector view and original cavity numbering for each physical ECU; the current source drawings lack this convention.
- Trace the communication transceiver routing and output drivers/conditioning. A harness wire is usually not a direct MCU wire.
- Resolve the B/Y and L/B interlock-network alternatives. The earlier fixed PB0/PB4 pairing was withdrawn after contradictory manual callouts; see the [route audit](../semantics/CONNECTOR_ROUTE_AUDIT.md).
- Identify the later O2 heater command, PT7 destination, ADC7 input and PB6/PB7 destinations. They are not assigned by elimination.

## Reproduce

Run `python scripts/build_pin_overview.py`, `python scripts/pin_families.py`, then `python scripts/test_pin_families.py` and `python scripts/test_pin_configuration.py --check`. CI also runs `python scripts/pin_families.py --check` to reject a stale report. [pin_audit.json](pin_audit.json) contains both family records, the exact-byte checks for each SHA-256, all 26/34 connector positions, source links and the flashing-sketch comparison.

The package transcription is independently recorded in [package_datasheet_review.json](../semantics/package_datasheet_review.json), against [NXP MC9S12T64, Figure 11, PDF 60](https://www.nxp.com/docs/en/data-sheet/9S12T64AF16V1.pdf#page=60). These checks preserve unresolved physical claims rather than automatically promoting them when software evidence passes.
