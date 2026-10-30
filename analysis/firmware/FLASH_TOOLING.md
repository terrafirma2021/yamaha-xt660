# ECU tools: readout, backup, flashing and map editing

The browser workbench provides **BIN inspection, unchanged-copy export, byte comparison, feature controls, raw-map draft editing, automatic startup-checksum correction**. [Feature controls and their evidence](FEATURE_PATCHES.md) cover immobilizer, PAIR commands and overrun fuel cut for both registered application families, plus O2 feedback and new O2 fault suppression in the late application. The early O2 row is read-only because feedback is not configured in those BINs. It does not yet perform ECU memory readout or flashing. A captured serial stream is not a firmware backup. The tool does not transmit serial bytes, modify originals or claim complete physical scaling.

## What the existing tools actually establish

The [per-ECU pin audit](PIN_AUDIT.md) compares the flashing sketch with both Yamaha connector drawings. The early manual has 26 positions; the later manual and 2C1-8591A-10 sketch have 34. Sketch terminals 3 / 7 / 12 correlate with later manual R / B/W / Y/L after horizontal reflection, but the sources do not establish connector view or manufacturer numbering. Those labels do not transfer to the early connector. SCI0 boot and SCI1 application evidence is checked separately for each BIN; physical transceiver routing remains unconfirmed.

### YamahaFlasher: direct XT boot evidence

The installed `YamahaFlasher.exe` extracted from Yamaha ECU V1 is a native x86 Visual Basic 6 program, 729,088 bytes, SHA-256 `706666bf83a737d2a4bc1965c662469fdb2e2d50c6ee01252d9d39065cb9b08c`. It was inspected without launching it or booting the VM. This executable provides **direct evidence for the recovered XT boot protocol**. Its form's default 16-byte session record exactly matches CPU FF10–FF1F in the populated companion boot. This is separate from the newer Yamaha service-tool library discussed below.

| Finding | Native executable evidence | Firmware comparison |
|---|---|---|
| XT660 selects the 64K reader/writer | XT660 selector at 4631F3 / 478FF7; method slots 718 / 71C; entry thunks lead to 469770 / 470910 | 16-bit address space; “64K” is the tool's operation name |
| Boot connection is 9,600 baud, 8N1 | Read baud call 46BB69, write call 472E4D; each receives immediate 2580. Data setup 46BC49–46BC6E and 472F2D–472F52 | SCI0 divisor 0068; confirms the target rate independently of oscillator inference |
| Session record matches exactly | Form `Text1` default: 32 ASCII hex characters at executable file offset 5F2F1; command header `01 00 00 15` | F913 compares the same 16-byte record at FF10 |
| Service transition | Sends `02 01 00 05 F8` after session exchange | F945 mode 1 disables application peripherals and enters the boot service loop |
| Memory reads | Builds command 03, mode 02, seven-byte request at 46F051–46F336 | F99A mode 2 returns 512 data bytes |
| Read coverage | Base 1800 at 46EF55; offset limit E7FF at 46EDE4; increment 0200 at 4702B4 | 116 blocks cover CPU 1800–FFFF: **59,392 bytes**, including F800–FFFF boot |
| Cable echo handling | Reader excludes first 7 received bytes; takes payload at one-based positions 12–523, checksum at 524 | Seven request bytes + 517-byte ECU reply; USB chunk boundaries are irrelevant |
| Programming | Command 09, parameter = address high byte, length 0805, 2048-byte payload; send at 477A16, increment 0800 at 478802 | FB63 erases the addressed 2 KiB span, programs staged RAM 1000–17FF and compares it with flash |
| Successful programming reply | UTF-16 hex string `09000005F2` at 4619E4 | Command 09, status 00, length 0005, negated-sum checksum F2 |

Addresses in the executable column are preferred PE virtual addresses, except the explicitly named file offset. The [machine-readable evidence](yamaha_flasher_evidence.json) records 50 native/data anchors. With your own copy of this exact executable, run `python scripts/verify_yamaha_flasher.py /path/to/YamahaFlasher.exe` to check its hash, anchors and session-record equality. The executable, license files and full decompilation are not distributed. Ghidra completed both large writer decompilations; both reader decompilations timed out. Reader findings above were checked in native instructions rather than inferred from incomplete pseudocode.

The first bulk-read request is `03 02 00 07 18 00 DC`; the last is for FE00. The reader also makes 16-byte probes at 7FF0 and F770. The writer makes probes at 7FF0, 1800 and 1820, then sends `05 01 00 09 08 20 5A A5 CA` to write the boot's special RAM gate at 0820. These observations establish protocol compatibility, not a complete hardware-tested connection sequence. The tool uses FTDI D2XX; its baud/data/read/write declarations match the [FTDI D2XX API](https://ftdichip.com/wp-content/uploads/2025/06/D2XX_Programmers_Guide.pdf). Web Serial needs its own transport implementation.

The write loop reaches the F800–FFFF boot block. Consequently a source with an FF placeholder there must not be treated as a complete programming image. Erase/program behavior is now traceable in both host and ECU code; ignition sequencing, all timeout/retry branches, adapter behavior and recovery still require reconstruction and a bench transaction. No live read or write was performed.

The independent [offline read module](../../site/assets/tools-boot.mjs) now builds that 116-block plan, separates explicitly configured cable echo from replies, checks command/status/length/checksum, and assembles exact addressed coverage without padding missing bytes. It preserves captured bytes, including a failing startup checksum. Tests cover every split position in a 524-byte transaction, one-byte chunks, malformed replies, truncation, extra bytes, duplicate/missing blocks and reconstruction of the unchanged companion BIN. It has no serial access or session/programming transmitter and is not yet wired into the browser connection button.

### Yamaha service-tool communication library

The supplied `YamahaServiceTool.Communication` project includes real reprogramming code, not just monitoring. In `Reprogram/Reprogram.cs`, `ReprogramPhase1` selects a programming session and performs seed/key access; `ReprogramPhase3` starts a routine, requests a download, sends bounded chunks with a transfer counter and exits the transfer; `ReprogramPhase4` requests a memory checksum and compares it against the reprogramming file. `Protocol/RequestDownload.cs` interprets the ECU-advertised maximum frame length.

Those paths use the library's KWP/CAN message layer and external file definitions. Their presence does **not** establish compatibility with this XT boot. Our boot dispatcher accepts command indices 0–15 and a different frame format. No manufacturer reprogramming files for these exact BINs, paired adapter/ECU capture or bench execution was supplied. The third-party source stays local; [the source audit](flash_tool_sources.json) records hashes and line locators.

The connection selection is concrete: `Communication.cs:2338`, `ConnectKLineReprogram(flagShare)`, chooses ISO14230 at **10,400 baud** when false and Meter14230 at **15,625 baud** when true, then calls the Yamaha PassThru fast-init operation. `ReprogramPostPhase1` selects that path from `ReprogramFileAttribute.DataLinks`. These KWP rates must not be confused with the recovered SCI0 boot's nominal 9,600 rate. `ReprogramFileAttribute` also supplies S-record content, address/data formats and checksum ranges/values; the project references external `RepFile`, `Dao` and `DaoManager` assemblies. The provided folder establishes a programming implementation, not an XT-specific definition for these BINs.

The KWP writer uses session 10/82, security access, a start routine, RequestDownload 34, TransferData 36 and RequestTransferExit 37, followed by checksum routines. `KLineRequest` wraps those in KWP headers with an additive checksum. In contrast, `ReadMemoryByAddress` and `RequestUpload` appear in enums/debug labels but have no request builder or complete dump loop in this supplied project; the corresponding `KLineResponse.cs:445–456` cases just break. Thus real write support in the library does not imply a ready-made full-memory reader. The known XT read handler remains command 03 in the separate boot protocol. Porting the library to a DIY serial interface also requires replacing its Yamaha adapter API transport, including fast-init behavior, with an appropriate electrical interface and verified timing.

The browser transport can use a COM/serial adapter through [Web Serial](https://developer.chrome.com/docs/capabilities/serial/). Its port chooser requires a user gesture. The interface must supply the correct electrical levels and routing; a serial API does not provide an automotive transceiver. Browser/adapter support for a requested baud rate must also be checked.

## Recovered boot framing

Scope: the populated boot at F800–FFFF in the [companion](xt660-2004-2006-companion/BOOT.md). Its 2,048 bytes are identical in five registered files. The four FF-filled files do not contain that boot and are not silently filled from a companion.

| Bytes | Interpretation | Instruction anchors |
|---|---|---|
| 0 | Command index, 00–0F | FE2C–FE35; dispatch table FF30–FF4F |
| 1 | Request parameter / response status | Receive storage at FE47–FE4B; handlers read 0803 |
| 2–3 | Total frame length, big endian, including checksum | FE4F–FE5D; transmit FDD6–FDE0 |
| 4 onward | Payload | FE60–FE74; read-response source FDE2–FDF8 |
| Final byte | Negated sum of preceding bytes, modulo 256 | FE7B–FE7E and FDFF–FE02 |

For well-formed host frames, the receive path checks length at the fifth received byte: maximum 0805, with the low length byte no greater than 1F. Payload of frames with a nonzero length high byte is staged at RAM 1000 onward; shorter payloads stay at 0806 onward. These receive bounds are not a generic permission to write arbitrary memory. The offline frame decoder accepts complete framing candidates; it is not an emulator of all malformed-message behavior or session checks.

The dispatcher gates most commands on session word 0024 = A55A. Command 01 compares a 16-byte record against FF10–FF1F, limits failed attempts, and disables SCI1 on success. Commands above 0C additionally require boot-loop state 0022 = 5A. The application and boot ports must therefore not be treated as interchangeable.

| Command | Handler | Static role |
|---|---|---|
| 00, 04, 06, 0A–0C | F904 | Default/rejection path |
| 01 | F913 | Session record comparison |
| 02 | F945 | Service-mode change / restart wait |
| 03 | F99A | Addressed read; transmitter reads from request address at 0806 |
| 05 | F9C8 | Byte/word memory write |
| 07 | F9E9 | Memory-window selection and optional 2 KiB RAM staging |
| 08 | FA35 | Compare staged data and update differing 512-byte sectors |
| 09 | FB63 | Additional erase/program and comparison path |
| 0D | FBFE | Copy erase template to RAM and execute |
| 0E | FC1F | Copy programming template to RAM and execute |
| 0F | FD1C | Destructive RAM self-test / full-ROM check and terminal loop |

Read mode 0 returns 2 data bytes; 1 returns 16; 2 returns 512; 3 returns 2048; 4 returns 256; the remaining selector path returns 1024. Response length is payload length + 5. The offline preview restricts selectors to 0–5 and rejects ranges that wrap the 16-bit address space. Example request for two bytes at CPU 1800: `03 00 00 07 18 00 DE`. This is a static framing example, **not a proven complete readout procedure**: session entry, timing, electrical routing and response behavior remain untested on hardware.

## Flash controller evidence and remaining work

The templates write command 40 to 0106 for sector erase and command 20 for word programming, then launch through 0105 bit 7 and inspect status bits. This is consistent with the conditional [MC9S12T64 flash-controller specification](https://www.nxp.com/docs/en/data-sheet/9S12T64AF16V1.pdf). It corroborates register meaning, not physical chip identity or a validated programming recipe. [NXP AN2153](https://www.nxp.com/docs/en/application-note/AN2153.pdf) describes serial bootloader and recovery considerations for a different S12 device; its sample protocol is not this Yamaha protocol.

Before enabling a live driver:

1. Establish the exact ECU interface and SCI0 electrical route; do not assume the SCI1 dashboard line reaches it.
2. Capture a successful session/read transaction with the adapter, baud, framing, direction and power sequence recorded.
3. Verify session entry and bounded reads; assemble addressed blocks with coverage tracking and compare two independent readouts.
4. Identify persistent-storage coverage separately. A 64 KiB file with an FF boot placeholder is not a complete recoverable ECU backup.
5. Validate erase boundaries, protection, RAM execution, watchdog behavior, interruption recovery and byte-for-byte post-write readback on recoverable bench hardware.

### Application and boot connection paths

| Evidence | Early family | Late family | Meaning |
|---|---|---|---|
| Application SCI1 divisor | 506E–5072: `CC0040 5CD0` | 4863–4867: same bytes | Divisor 64 at SCI1 D0–D1 |
| Application polls boot service | 53C8: `16F8A0` | 4C06: same bytes | Boot dispatcher can run from the application loop |
| Populated boot initializes SCI0 | F86E–F872: `CC0068 5CC8` | Identical populated boot | Divisor 104 at SCI0 C8–C9 |
| Successful boot session | F93B–F93D: `87 5AD3` | Identical populated boot | Clears SCI1 control; boot traffic continues on SCI0 |

These instruction anchors are checked against every applicable registered BIN. The four FF boot placeholders supply no boot evidence. The application loop also conditionally disables SCI0: early 53BB–53C0 and late 4BF9–4BFE inspect boot state bit 0020:04. Application protocol handling can set that bit (early CE70, late C4E0). Thus session timing and state matter; opening a serial port alone is not ECU identification or entry into programming mode.

The [MC9S12T64 specification, SCI section](https://www.nxp.com/docs/en/data-sheet/9S12T64AF16V1.pdf#page=424) gives baud = bus clock / (16 × divisor). Its table on PDF page 437 explicitly lists divisor 104 at a 16 MHz bus as 9,615 actual baud for a **9,600-baud target**, with 0.16% error. Divisor 64 yields 15,625 at that bus rate, matching `Communication.cs`'s `ConnectMeter` request (`Baud15625`, lines 1585/1592). Consequently **15,625 for meter/diagnostics and nominal 9,600 for boot** is supported by the register settings. YamahaFlasher's direct 9,600-baud API calls now independently confirm its requested boot rate; actual adapter/ECU operation remains untested here. Users should not have to enter these rates manually once each connection profile is validated.

The workbench currently exposes no live serial connection. There is no evidence here of a command that simply switches the dashboard wire to a flashing baud. SCI0 and SCI1 are separate MCU interfaces: conditional 80-pin-package PS0/RxD0 and PS1/TxD0 (67/68), versus PS2/RxD1 and PS3/TxD1 (69/70). Physical routing through the ECU PCB/transceiver to a connector remains unresolved. Existing decompiler warnings around overlapping instructions and flash return flags must also be resolved before trusting live retries.

## Workbench behavior and tests

The repository BIN picker opens any of the nine registered images directly, without a local upload. The site packages unchanged copies of those public repository files and checks each downloaded file's size and SHA-256 against the catalogue before enabling inspection or editing. Original and modified variants remain separate choices. Identity and change reports record whether the source was a repository BIN or a local file; neither source is a live ECU readout.

Only exact registered SHA-256 inputs enable editing. The layout belongs to the loaded BIN, not the globally selected bike. The original buffer is immutable; editing is limited to declared map cell bodies with checked addresses, big-endian widths and integer bounds. Unknown files can be inspected and compared but do not inherit map layouts or automatic checksum correction. A draft and its JSON change report are separate downloads.

All nine registered images share the recovered startup rule: sum big-endian words over CPU 1800–F7FF modulo 65536, expecting AA55. The early caller/routine are 5358/A489; the late equivalents are 4B65/971D. Runtime checks match their caller and summation/compare instruction bytes plus the 5AA5 trailer marker before enabling correction. The untouched source is checked separately from the editable copy. The copy is corrected on open, after edits, undo and discard, and checked again before export; export is stopped if its supported startup checksum does not pass.

Correction uses the existing project's **analyst-selected compensation word at F7FC**, not a newly identified manufacturer checksum field. Each source has FFFF there except the existing corrected image's FF7F. Tests check no overlap with decoded instructions, static targets or map edits; correction is confined to that word, preserving the F7FE marker and boot bytes. The calculation is `new_word = (old_word + AA55 - current_sum) mod 65536`. Undo/discard restores calibration values while keeping the copy's startup checksum corrected; save-untouched retains the exact original, even when its checksum fails. Change reports include source/draft results and compensation changes. This verifies the startup check only; it does not establish hardware compatibility or repair the alternate full-ROM check. See [the original correction analysis](../semantics/CHECKSUM.md).

The workbench follows Connect → Read & verify → Edit & save → Flash & verify. Live ECU actions remain disabled. The diagnostic capture panel, raw-byte terminal, standalone byte inspector and command preview have been removed from the interface. Offline decoder and receive-transport modules remain in the source and tests for development; the browser workbench does not load the receive transport or request a serial port. Saving edits and flashing are separate actions; Flash ECU remains disabled.

Run `node scripts/test_tools.mjs` for byte-level editing, checksum, framing and mocked serial lifecycle tests. These are software tests, not ECU or adapter validation.
