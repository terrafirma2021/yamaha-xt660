# Yamaha XT660 ECU Research

Firmware analysis, TunerPro definitions, flashing tools and ECU emulation for the Yamaha XT660 family.

**[Website](https://terrafirma2021.github.io/yamaha-xt660/) · [Browser emulator](https://terrafirma2021.github.io/yamaha-xt660/emulator/) · [Downloads](https://github.com/terrafirma2021/yamaha-xt660/releases)**

## Start here

- **Explore the ECU:** select a motorcycle and firmware on the [website](https://terrafirma2021.github.io/yamaha-xt660/) to browse its maps, connector diagrams, MCU pins and research.
- **Edit a BIN:** download its matching [BIN and XDF](https://terrafirma2021.github.io/yamaha-xt660/xdf/) and use TunerPro. Definitions include map tables and supported feature patches. [XDF instructions](definitions/README.md).
- **Read or write an ECU:** the [Windows Flash Tool bundle](https://github.com/terrafirma2021/yamaha-xt660/releases/tag/v0.2.2) includes the tool, nine BINs and nine XDFs. It uses a USB KKL interface, saves backups and checks compatibility, checksums and readback. [Flashing instructions](flasher/README.md).
- **Run the firmware:** use the [browser emulator](https://terrafirma2021.github.io/yamaha-xt660/emulator/) with no installation, or the [Windows emulator](https://github.com/terrafirma2021/yamaha-xt660/releases/tag/emulator-v0.1.0). Key, starter, throttle, neutral, sensor faults and diagnostic controls act on the emulated ECU. The dash reads its K-line replies. [Emulator instructions and source](emulator/README.md).

## Current coverage

The library contains **nine registered BINs across two application families**, with application decoding and separate calibration catalogues for each image: **71 maps per early image and 86 per later image**. Supplied files retain their recorded hashes; corrected copies are identified separately.

The emulator runs the **five images with complete boot code**. The other four have missing boot content and are not supplied with donor code. Its HC12 core runs independently of dashboard rendering. Closing or refreshing the browser version ends its session; the Windows process can continue without its dashboard.

The model dataset covers XT660R, XT660X and XT660Z Ténéré. **No matched XT660Z BIN is currently available.** Model, year and ECU associations retain their evidence and qualifications; shared code or a catalogue replacement part does not establish interchangeability.

Some physical map scales, absolute spark reference and connector-to-MCU wiring remain unresolved. The flash tool is a **bench-test prerelease** with software validation; physical ECU/adapter validation is pending. Emulation checks firmware behaviour, not combustion, AFR or power output. See the [research audit](analysis/REPOSITORY_AUDIT.md) and [verification ledger](analysis/semantics/VERIFICATION_LEDGER.md) for the evidence behind each claim.

## Source and research

| Area | Contents |
|---|---|
| [Firmware](firmware/registry.json) | BIN identities, hashes and provenance |
| [Dataset](dataset/README.md) | Model, market, ECU and source records |
| [Application analysis](analysis/firmware/FAMILY_DECODING.md) | Code families, disassembly and calibration differences |
| [Control systems](analysis/semantics/README.md) | Fuel, ignition, sensors, diagnostics, checksums and immobilizer |
| [Pin audit](analysis/firmware/PIN_AUDIT.md) | Per-BIN MCU and connector evidence |
| [XDF generator](definitions/README.md) | Regenerate definitions when findings change |
| [Flash tool](flasher/README.md) | Windows application, protocol and checks |
| [Emulator](emulator/README.md) | Browser/Windows builds, core sources and validation |

## Build the website locally

```sh
python -m pip install -r site/requirements.txt
python scripts/build_pages.py
python scripts/verify_pages.py
python -m http.server --directory _site 8000
```

Open `http://localhost:8000/`. Pages publishing checks the generated site and stored evidence; full firmware regressions and emulator compilation run separately. Build instructions for each tool live with its source.

To contribute another BIN, follow the [image import workflow](firmware/ADDING_IMAGES.md). Include its provenance and ECU identification where available. New images do not inherit existing map or wiring claims automatically.

Independent research project, not affiliated with Yamaha. [Asset credits](site/ASSET_CREDITS.md). The [emulator licence](emulator/COPYING) does not grant rights to the supplied Yamaha firmware.
