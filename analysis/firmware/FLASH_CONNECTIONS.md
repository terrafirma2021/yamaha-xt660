# Flashing connector references

The website separates **Flashing** (connections, backup and file checks) from **Tune** (feature and map edits, automatic startup-checksum correction, BIN and XDF export). Live connection, ECU reading, writing and readback remain unavailable. No hardware operation was added by this layout change.

## Two independently supplied references

The owner's extracted `Yamaha ECU Tools/xt660 ecu pinouts` folder contains two references. They are redrawn as connector grids; the photographs are retained as sources rather than used as the working diagram.

| Reference | Connector | Power | Ground | Communication |
|---|---|---|---|---|
| [XT660 / MT03 2005–2008 photograph](../../site/assets/references/xt660-early-flashing-photo.png) | 26 positions, two rows of 13 | Upper 3 | Upper 7 | Upper 12 |
| [XT660 2012 / 2C1-8591A-10 sketch](../../dataset/sources/xt%20660%20r/XT660_PinOut.JPG) | 34 positions, two rows of 17 | Sketch 3 | Sketch 7 | Sketch 12 |

The early source filename was `334550210_908575740348949_6886937403634831296_n.png`; the later folder copy was `273177169_5731490293544337_2636280349225232554_n.jpg`. These are supplied third-party annotations, not manufacturer-approved programming instructions or recordings of a successful bench session.

The early photograph shows the ECU connector's mating face, with its latch above. Its caption does not prove all XT660/MT03 ECUs from 2005–2008 share that housing; there is no ECU part-number label in the photograph. The later sketch explicitly labels 2C1-8591A-10 but does not identify mating-face versus wire-entry view. That distinction remains visible beside its redraw.

Both references independently identify the same three upper-row indices, despite their different total widths. This is not a transfer of the 34-position sketch's numbering to the early ECU. U/L numbers on the new diagrams are research coordinates, not OEM cavity numbers.

## Correlation with Yamaha manual drawings

The supplied flash references run horizontally opposite to the [2004 manual](https://scootertuub.nl/motoren/Yamaha/Yamaha%20XT%20660%20R%20X%202004%20Service%20Manual%20%20.pdf#page=462) and [2007 supplement](https://www.motomatrix.co.uk/yamaha-pdf/XT660X-R2007_Suppl_manual.pdf#page=81). The redraw's wire labels are a reflected **manual overlay**, not text visible in the early photograph.

| Signal | Flash redraw | Early manual | Later manual | Yamaha wire |
|---|---|---|---|---|
| +12V | U03 | U11 | U15 | R, red |
| GND | U07 | U07 | U11 | B/W, black/white |
| K-line / communication | U12 | U02 | U06 | Y/L, yellow/blue |

The ground highlighted by both flash references is B/W. The manuals also show a black ground at their lower-right position; neither supplied flash reference identifies that as an additional bench lead. The diagram does not invent power, ignition or enable connections absent from its sources.

The website associates each of the nine BIN records and its motorcycle profiles with the separately reviewed early or late reference. A labelled 2C1-8591A-10 drawing, a model photograph and an application-family-only association receive different labels. Firmware similarity does not establish physical connector fitment, and the image's broad year caption is never used to override the selected BIN family.

## USB KKL breakout

The connection schematic uses the [GuzziDiag / IAWDiag project's USB-KKL adapter table](https://www.guzzidiag.de/), which specifies OBD terminal 16 for +12V, 4 or 5 for ground, 7 for K-line and 15 for L-line. That source establishes the cable-side convention, not Yamaha ECU compatibility.

| Circuit | ECU reference | KKL breakout |
|---|---|---|
| External fused +12V | Upper 3 | OBD 16 |
| Shared supply negative | Upper 7 | OBD ground 4 / 5, according to the cable's wiring |
| Communication | Upper 12 | OBD 7 |

The KKL panel is a schematic of **numbered breakout terminals**, not a mirrored plug-face drawing. Identify terminals from the breakout's moulded numbers. The external supply powers the ECU and the adapter's vehicle interface; USB does not supply ECU power. L-line 15 is unused in this reference. Colours identify functions, not the physical cable conductor colours.

The recovered flashing tool requests 9,600 baud / 8N1. The [serial-port audit](PIN_AUDIT.md) still distinguishes SCI0 boot code from SCI1 application communication. The new photograph does not establish their internal transceiver routing or complete power-on/session sequence.

## File checks and reproducibility

Flashing can inspect unchanged repository BINs and local files, recognise the same bounded map/feature modifications as Tune, report the startup checksum and boot coverage, and compare a second file byte-for-byte. It does not repair a captured backup. Unknown code changes and missing boot bytes do not become a verified image because the file has the expected size. A passing checksum never enables live writing.

`scripts/site_flashing.py` builds both connector grids from `pin_audit.json`, preserving manual coordinates and hashing the original references. It emits `flashing/connections.json`. `scripts/test_flashing.mjs` checks both layouts, every matched profile, all nine files, edited-file recognition, unknown changes and unchanged-byte inspection. `scripts/verify_site_routes.py` checks the separate pages and every model-specific route. Old `/tools/` bookmarks redirect to the appropriate workspace.
