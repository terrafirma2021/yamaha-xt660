# ECU tools: readout, backup, flashing and map editing

The browser workbench provides **local BIN inspection, unchanged-copy export, byte comparison, raw-map draft editing and receive-only serial capture**. It does not yet perform ECU memory readout or flashing. A captured serial stream is not a firmware backup. The tool does not transmit serial bytes, modify originals, repair checksums automatically or claim complete physical scaling.

## What the existing tools actually establish

The supplied `YamahaServiceTool.Communication` project includes real reprogramming code, not just monitoring. In `Reprogram/Reprogram.cs`, `ReprogramPhase1` selects a programming session and performs seed/key access; `ReprogramPhase3` starts a routine, requests a download, sends bounded chunks with a transfer counter and exits the transfer; `ReprogramPhase4` requests a memory checksum and compares it against the reprogramming file. `Protocol/RequestDownload.cs` interprets the ECU-advertised maximum frame length.

Those paths use the library's KWP/CAN message layer and external file definitions. Their presence does **not** establish compatibility with this XT boot. Our boot dispatcher accepts command indices 0–15 and a different frame format. No manufacturer reprogramming files for these exact BINs, paired adapter/ECU capture or bench execution was supplied. The third-party source stays local; [the source audit](flash_tool_sources.json) records hashes and line locators.

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

For well-formed host frames, the receive path checks length at the fifth received byte: maximum 0805, with the low length byte no greater than 1F. Payload of frames with a nonzero length high byte is staged at RAM 1000 onward; shorter payloads stay at 0806 onward. These receive bounds are not a generic permission to write arbitrary memory. The offline frame viewer accepts complete framing candidates; it is not an emulator of all malformed-message behavior or session checks.

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

The nominal boot divisor is 0068 (about 9,615 baud at a 16 MHz bus), whereas the application divisor is 0040 and the supplied tool requests 15,625 baud for the legacy meter link. Neither establishes a cable's pin route. Existing decompiler warnings around overlapping instructions and flash return flags must be resolved against disassembly before trusting a live error/retry state machine.

## Workbench behavior and tests

The repository BIN picker opens any of the nine registered images directly, without a local upload. The site packages unchanged copies of those public repository files and checks each downloaded file's size and SHA-256 against the catalogue before enabling inspection or editing. Original and modified variants remain separate choices. Identity and change reports record whether the source was a repository BIN or a local file; neither source is a live ECU readout.

Only exact registered SHA-256 inputs enable editing. The layout belongs to the loaded BIN, not the globally selected bike. The original buffer is immutable; editing is limited to declared map cell bodies with checked addresses, big-endian widths and integer bounds. Unknown files can be inspected and compared but do not inherit map layouts. A draft and its JSON change report are separate downloads. Draft checksums are reported, not repaired; see [the qualified original checksum correction](../semantics/CHECKSUM.md).

Receive capture has a 2 MiB bound, timestamped USB chunks, disconnect handling and explicit save. It has no writer API. USB chunks do not imply packet boundaries. A new connection replaces the previous in-memory capture. The inspector requires explicitly delimited application or boot frames and refuses bad lengths/checksums.

Run `node scripts/test_tools.mjs` for byte-level editing, checksum, framing and mocked serial lifecycle tests. These are software tests, not ECU or adapter validation.
