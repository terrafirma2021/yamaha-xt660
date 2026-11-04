# XT660 firmware emulator

Run the registered BINs on a locally patched µCsim HC12 core. The five complete images execute from reset with modeled ADC, GPIO, timers, interrupts, SPI storage and both serial interfaces. The four images without boot code are rejected; donor boot bytes are never inserted.

The local dashboard provides raw sensor inputs, synthetic crank pulses, coil/injector traces, authentication and meter exchanges, Run/Pause/Step, trace export and a firmware-integrity check. It is separate from the reference website and never opens a COM port.

## Build and start

Linux/WSL needs Python 3, Git, make, g++, autoconf, bison, flex and ncurses development libraries. The build does not install system packages. From this repository:

```sh
python3 emulator/build.py --directory /root/xt660-ucsim
python3 emulator/dashboard.py --ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu
```

Choose a directory writable by your account. On Windows, build inside WSL, then launch from PowerShell:

```powershell
python emulator/dashboard.py --wsl --ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu
```

Open **http://127.0.0.1:8766/**. Load a BIN, authenticate the fixture if enabled, send crank revolutions and press Run. Sensor inputs can change while running. Pause stops instruction batches; Stop crank removes the external pulses. Use Step to watch the firmware detect pulse loss. Loading another BIN resets the simulated ECU.

The server binds only to loopback. It uses bundled HTML/CSS/JavaScript, a per-session request token and same-origin checks. It has no upload, arbitrary debugger-command or physical-port endpoint. Close it with Ctrl+C.

## What is being executed

- Startup and application instructions come from hash-checked source BINs. Normal engine runs leave every one of the 59,392 flash bytes unchanged.
- The storage defaults are produced by executing each BIN's own factory initializer in an isolated session. All five produce the same 512-byte fixture, SHA-256 `93f11ba1d85ba762b87ee17ba9e9434e1bb8c81d6df23b238892f94f77fb68f6`. This is not an EEPROM read from a motorcycle.
- A separate synthetic registration record supplies `ABC` three times and trailer `5AA5` at external-storage offsets `50–5A`. Authentication runs through actual SCI receive interrupts, main-loop calculations and replies. No runtime flags or authentication branches are patched. The supplied immo-off BIN correctly skips authentication.
- SCI1 exercises the challenge/response sequence and normal `FE` / `01` meter requests, with reply checksum checks. Corrupt authentication responses are tested separately.
- PT1 receives ten ordinary tooth intervals and one double interval per synthetic revolution. This follows the recovered gap detector, not a measured rotor trace. The firmware selects the /32 timer prescaler. Both families synchronise, generate PT3 coil and PT6 injector transitions, and detect pulse loss.

Inputs remain **raw ADC counts and timer ticks**. The oscillator, analogue conditioning and mechanical TDC reference are not established by running code. The UI does not invent RPM, °C, throttle percentage or absolute ignition advance. Output transitions are electrical command states in the MCU model, not combustion, torque or actual coil current. PT7 is displayed as a secondary code-path output without claiming a second XT cylinder.

## Flash-client integration

`boot_service.py` runs the actual boot instructions and RAM-copied flash routines. It injects SCI0 bytes at the modeled divisor and collects the actual transmitted reply. It does not replace boot handlers with Python functions.

Execution exposed a bank-selection problem in the former desktop write plan. Command `09` fixes BKSEL to bank 1 and rejects an upper-bank target. Command `0D` copies the erase loop to RAM and erases **1800–F7FF**, preserving **F800–FFFF**. Command `0E` programs an already-erased 2 KiB block from RAM and selects its bank from the target address. The revised desktop client uses `0D` plus all 28 application blocks through `0E` whenever an upper-bank block changes. Lower-bank-only changes can still use `09`.

The C# integration bridge substitutes only the byte transport. The real `BootClient` and `FlashService` perform two full reads, an immutable disk backup, a map edit with checksum correction, programming, per-block readback and complete final readback. Simulation gets longer host timeouts; the production client's baud and timeouts are unchanged. Physical cable/ECU operation remains untested.

```powershell
python emulator/test_emulator.py --wsl --ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu
./flasher/build.ps1
python scripts/build_release.py
./scripts/test_desktop_protocol.ps1
./scripts/test_desktop_emulator.ps1 -Ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu
```

Tests write detailed logs under ignored `.runs/`. [validation.json](validation.json) records the integrated firmware and controller checks; [desktop-validation.json](desktop-validation.json) records the C# integration separately. [dashboard-validation.json](dashboard-validation.json) records the browser checks. None is a hardware certificate.

## Debugging and automation

```powershell
python emulator/run.py --wsl --ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu --console --image xt660-2c1-10
```

The console starts at reset with a breakpoint at that BIN's application entry. Tested commands include:

```text
run
step
next
info registers
break 0xf816
break rom w 0x0886
break rom r 0x1200
info hardware xtboot
quit
```

Conditional breakpoints, hit counts, read/write watchpoints and JSR step-over work at assembly level. [µCsim commands](https://www.ucsim.hu/cmd.html). Python's `Engine` API exposes bounded instruction stepping, ADC/GPIO fixtures, crank generation, serial exchange, RAM snapshots, storage export and immutable-flash verification.

The older `run.py --runtime`, `--crank` and `--sensors` modes remain reproducible isolated fixtures. They use disconnected SPI/idle serial unless their fixture says otherwise; use the dashboard or `Engine` for initialized storage and an authenticated peer.

Debugger fixture controls are separate from MCU registers:

| Control | Meaning |
| --- | --- |
| `adc0` … `adc7` | 10-bit input counts, 0–1023 |
| `xtboot_0_cfg[9..14]` | External PA/PB/PE/PT/PS/PP levels |
| `[15..16]` | PK7 and PTAD external levels |
| `[17..18]` | SPI external byte and mode: disconnected, loopback or storage |
| `[19..25]` | PT1 interval, low width, gap index/multiplier, edge count, run, trace |
| `[26..29]` | SCI0/1 incoming bytes and external-peer clock divisors |
| `[30..33]` | SCI transmit counts and last bytes |
| `[34]` | Enable simulated flash commands; off in normal engine runs |
| `eeprom[0..511]` | Persistent external-storage fixture bytes |

## Model boundaries

The conditional MCU reference is [MC9S12T64 Rev 1.1.1](https://www.nxp.com/docs/en/data-sheet/9S12T64AF16V1.pdf). The model covers the firmware-used 8N1 SCI paths, SPI master transfers and observed storage protocol, ADC sequencing/formatting, GPIO directions/latches, ECT compare/basic capture, RTI, PLL status, watchdog servicing and maskable interrupts. Flash checks cover bank selection, sector erase, word programming, protection, errors and busy-bank access.

It is a functional model with instruction-boundary peripheral updates. PLL acquisition, storage busy and flash busy durations are deterministic fixtures. Exception-entry timing, analogue settling and oscillator frequency are not calibrated. Unsupported modes stop explicitly: banked CALL/RTC, advanced ECT buffering/pulse accumulators, external ADC triggering, SCI parity/9-bit/break and unused PWM modes. Watchdog reset requests stop with a reason rather than restarting the MCU. It is not a model of every silicon function or every physical fault.

Local core fixes cover decrement width, indexed addressing, flags, bit branches, MOV auto-index updates/disassembly, CCR X-mask transfers, loop decoding, ticks and step-over metadata. Builds pin µCsim commit `59a14ff99efe7e92474faf4c4ddf57b5e4ff0631`, verify known patch states and preserve unrecognised local edits. **No upstream submissions have been made.**

## License

The emulator and µCsim-derived patches use GPL-2.0-or-later; see [COPYING](COPYING). µCsim remains credited to its upstream authors. This does not assign a license to Yamaha firmware.
