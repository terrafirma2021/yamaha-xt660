# XT660 Flash Tool

`XT660.FileTool.exe` is a portable Windows COM-port application. It uses a USB KKL interface at 9,600 baud / 8N1; there is no user baud setting. Windows needs .NET Framework 4.x and the cable's serial driver.

- **Connect** opens the selected COM port, prompts for ECU power and sends the recovered session and service-mode frames.
- **Read ECU** reads CPU `1800–FFFF` twice and saves a 59,392-byte BIN only when both reads match. Its original checksum is reported; backup bytes are never corrected.
- **Write ECU** loads a recognised BIN, validates and automatically corrects the startup checksum, asks for confirmation, reads the connected ECU twice, saves the backup, matches the application, programs changed 2 KiB blocks and verifies readback. The original input file is unchanged.
- **Pinouts** shows the website's 26-pin and 34-pin connector redraws and KKL wiring. No year selection or source photographs are included. K-line is yellow.

**Bench-test prerelease:** the serial implementation and error handling are software-tested. No physical ECU/adapter transaction has been performed here. Software completion does not mean hardware qualification. Connector-view limitations remain beside the diagrams.

## Write boundaries

Only CPU `1800–F7FF` is programmed. The real ECU boot is read and must match the reviewed boot shared by five registered BINs. It is never erased, replaced or supplied from a donor. An input with the known FF boot placeholder can provide the application, but cannot replace the real boot. Other populated boots are rejected. Bytes below CPU 1800 in a 64 KiB input are not part of this programming operation. This is an application writer, not boot replacement or BDM recovery.

Before the first erase, two complete matching reads are saved and checked on disk under `%LOCALAPPDATA%/XT660/Backups`. Compatibility requires that the connected application and prepared BIN match a common reviewed reference outside supported map/feature/compensation changes; a shared filename or family label is insufficient. Unknown code and incomplete patches block writing.

The startup sum is big-endian words over CPU `1800–F7FF`, modulo 65536, expected `AA55`. Automatic correction uses the reviewed compensation word at `F7FC`, preserves the trailer and verifies the result. It does not repair the alternate full-ROM test or add missing boot data.

Each response requires the expected command, status, length and packet checksum. Cable echo is detected from the session frame's distinct full header and validated byte-for-byte; it is fixed for that connection. Reads have one outstanding request. A timeout, malformed reply, extra data, rejected command or readback mismatch stops the operation. Erase/program commands are never automatically retried. Cancel is unavailable after a write is confirmed; the window cannot close during writing/verification.

The [protocol evidence](../analysis/firmware/FLASH_TOOLING.md) links the original YamahaFlasher native instructions to the ECU boot handlers. `BootProtocol.cs` is a new implementation of that XT boot format, not a generic KWP/UDS flasher. The transport uses the [.NET SerialPort API](https://learn.microsoft.com/en-us/dotnet/api/system.io.ports.serialport?view=netframework-4.8.1), binary reads/writes, bounded timeouts and no hardware flow control.

## Build and check

```powershell
./flasher/build.ps1
python scripts/build_release.py
./scripts/test_desktop_protocol.ps1
python scripts/test_desktop.py
```

The protocol test executable uses an independent byte-stream ECU fixture; it never opens a COM port. Tests cover both echo modes, fragmented replies, all nine input layouts, backup failures, mismatched reads, incompatible applications/boots, protected address bounds, checksum correction, changed-block writes, per-block and complete readback, negative replies and no destructive retries. The file tests cover the compiled release executable and all 427 XDF patch presets. Native TunerPro feature-patch application remains untested at the owner's request.

The release includes nine unchanged source BINs, nine XDFs, the EXE, a manifest, font licences and SHA-256 hashes. Yamaha branding, Barlow/Barlow Condensed fonts and both connector drawings are embedded in the EXE. Build output is ignored by Git. Third-party flashing executables are not redistributed. `build_flasher_resources.py` obtains both connector drawings from the same source data as the website.

Offline CLI commands remain available:

```
XT660.FileTool.exe --verify-bundle
XT660.FileTool.exe --inspect edited.bin
XT660.FileTool.exe --fix edited.bin corrected.bin
XT660.FileTool.exe --compare backup.bin readback.bin
```

The CLI never connects to a COM port. Exit codes: 0 success, 1 error, 2 comparison mismatch. `--fix` preserves its input and refuses to overwrite a registered source BIN.
