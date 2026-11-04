# XT660 XDF downloads

Ready-made TunerPro XDFs are generated for all nine registered BINs. Use the [website library](https://terrafirma2021.github.io/yamaha-xt660/xdf/) to download the matching pair, or use [manifest.json](manifest.json) to identify the exact source BIN, file size and SHA-256.

Regenerate after updating the per-BIN map findings:

```sh
node scripts/build_xdfs.mjs
node scripts/build_xdfs.mjs --check
python scripts/test_xdf_export.py
```

The website publishes these files directly. Definitions contain raw map tables and reversible feature patches. Use TunerPro's Apply/Remove on the whole patch. For speed offsets, remove the active patch before choosing another. Unsupported early O2 controls are omitted.

Automatic TunerPro checksum correction and unresolved physical conversions are not included. The [Windows Flash Tool](../flasher/README.md) validates and corrects the startup checksum before writing. To save a corrected copy without connecting to an ECU, use its offline command:

```powershell
.\XT660.FileTool.exe --fix edited.bin corrected.bin
```

[Definition details and native verification](../analysis/firmware/XDF_DEFINITIONS.md).
