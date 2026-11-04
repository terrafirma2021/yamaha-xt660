# XT660 desktop tools

`FileTool.cs` builds a portable Windows application for BIN identification, checksum correction and file comparison. It uses the BINs and XDFs from the release bundle. No installation, network connection or administrator access is required; Windows must have .NET Framework 4.x.

This release is a **file-tools preview, not a working ECU flasher**. It does not open a COM port. Boot transport research and offline protocol tests are retained in `core/`; session entry and live erase/program/readback still need implementation and bench validation.

Run `./flasher/build.ps1`, then `python scripts/build_release.py`. The package contains all nine registered source BINs, their generated XDFs, hashes and `XT660.FileTool.exe`. Third-party flashing executables are not redistributed.

The desktop application checks bundle hashes on startup. Unknown code and partial patches block checksum saving. Correction writes a separate file, changes only the reviewed compensation word at CPU `0xF7FC`, and verifies the saved bytes. Map and complete feature-patch edits are recognised; a matching layout does not establish physical ECU fitment.

Command-line use:

```
XT660.FileTool.exe --verify-bundle
XT660.FileTool.exe --inspect edited.bin
XT660.FileTool.exe --fix edited.bin corrected.bin
XT660.FileTool.exe --compare backup.bin readback.bin
```

Exit codes: 0 success, 1 invalid input/error, 2 comparison mismatch. `--fix` rejects overwriting the input or an existing registered source BIN. Run `python scripts/test_desktop.py` to test the compiled application against every registered image and every XDF patch.
