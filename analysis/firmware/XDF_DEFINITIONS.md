# TunerPro definitions

The [XDF library](https://terrafirma2021.github.io/yamaha-xt660/xdf/) provides a generated definition for each registered BIN. Editing takes place in TunerPro. The website provides read-only research, XDF downloads and bench connection references.

Download an XDF together with its matching BIN, open the BIN in TunerPro and select the XDF. Save edits to a separate file. The Windows file tool in the [release bundle](https://github.com/terrafirma2021/yamaha-xt660/releases/tag/v0.1.0) can identify a supported edited layout, check its startup sum and save a checksum-corrected copy. It leaves the opened file unchanged. Live ECU reading and writing remain unavailable.

## Generated from the research

`node scripts/build_xdfs.mjs` reads the registered image identities and each image's decoded map catalogue. It checks the source SHA-256, applies the image's file base, and generates the files under [definitions](../../definitions/README.md). Run it after updating map findings; users do not need to create definitions themselves. `--check` rejects stale outputs. The website build checks and publishes those same files.

The manifest records each BIN's identity, length and base, its XDF digest, and its map/cell counts. There are nine definitions, containing 699 per-image map records and 69,575 cells. The early images have 71 maps each; the later images have 86.

XDF 1.70 tables use file offsets, unsigned big-endian cells and raw identity conversion `X`. The 65,536-byte and 59,392-byte formats have different offsets and are not interchangeable. Axes are fixed labels from the corresponding map catalogue. Physical scaling remains incomplete. Reversible XDFPATCH entries include the supported feature recipes and speed-offset presets. An automatic TunerPro checksum plugin is not included.

## Verification

`python scripts/test_xdf_export.py` independently parses all nine generated files and checks every table's dimensions, addresses, cell widths, axis labels and source values. `node scripts/test_tunerpro_capture.mjs` checks the recorded native TunerPro evidence against the current exporter and source files.

The [native capture](tunerpro_capture.json) covers representative 8-bit and 16-bit edits in both file formats using TunerPro 5.0.9786. All 1,350 copied values from the early fuel table match its saved BIN. The 915 → 916 edit changed only byte 0x1B67. The later 3 → 4 edit changed only file offset 0x00EE, corresponding to CPU address 0x18EE. Both edited files were accepted by layout matching and checksum correction; their original files were preserved. These observations do not claim a native inspection of every map or establish physical units.

TunerPro saved the edits without repairing the startup checksum. The flashing file-preparation function checks the instruction anchors and selected layout before producing a separate corrected copy, verifies `AA55` afterward, and preserves all bytes outside the reviewed compensation word at CPU F7FC–F7FD. See [checksum evidence](../semantics/CHECKSUM.md).

## Feature patches

The Features category contains PAIR disable, immobilizer disable, targeted overrun disable, later-family O2 disable, sidestand disable, lean-angle disable, CO full-range override and speedo disable. Early O2 is omitted because no supported switch exists. Forty nonzero speed offsets (-20 to +20) are separate guarded presets: remove one before applying another. Zero offset is the stock state.

Each XDFPATCH entry records exact base and replacement bytes at file offsets. Multi-address recipes stay together. Existing immobilizer-off images therefore start with that patch applied. Map values and code recipes are unchanged from the reviewed implementation. Native map import/edit/save evidence below predates the feature additions; it does not claim native patch application was tested. Patch XML is independently parsed and compared with the existing byte writers, then tested through the compiled desktop matcher. Physical operation remains unvalidated.

Patch serialization follows TunerPro's XDFPATCH/XDFPATCHENTRY format, including `basedata`; see the [definition format implementation](https://github.com/OpenEEC-Project/SAD806x/blob/master/SADXdf.cs) and the [author-published patch definition](https://github.com/YOU54F/PoloG40Digifant/blob/master/G60_TunerProWinOLS/TunerPro%20RT%20v5%20-%20G60%203%20Ignition%20Map%20%28Marc%20G60T%202014%29.xdf).
