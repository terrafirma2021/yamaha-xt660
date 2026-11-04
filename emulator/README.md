# XT660 firmware emulator

Run the registered BINs on a locally patched µCsim HC12 core. The five complete images execute from reset with modeled ADC, GPIO, timers, interrupts, SPI storage and both serial interfaces. The four images without boot code are rejected; donor boot bytes are never inserted.

The cockpit has key, run/stop, starter, N/1 and throttle controls. Its instruments consume checked SCI1 meter replies. Sensor faults, diagnostic buttons, raw inputs, coil/injector traces and trace export are available alongside the cockpit. It never opens a COM port.

## Run in your browser

[Open the emulator](https://terrafirma2021.github.io/yamaha-xt660/emulator/). Select an ECU, turn the key and press Start. No installation, Python, WSL or local ECU server is needed. All assets are served by the site; no third-party scripts are loaded.

The same C++ HC12 core, peripherals and meter peer compile to WebAssembly. A dedicated Web Worker owns instruction execution and the simulation clock. Dashboard rendering and snapshot polling do not advance or pause the MCU. Pause simulation is explicit. Closing or refreshing the tab ends this session; browser suspension can also pause execution. On resumption, the worker continues from its last instruction without inventing missed time. Storage survives key cycles within the session, and can be exported before closing it.

All five complete BINs measured approximately **1.00× real time** in Chrome on the test Windows PC at the nominal 16 MHz profile. Other devices may be slower; the cockpit reports the measured rate. [Browser validation](wasm-validation.json) records the 34 exact Windows checkpoint comparisons, diagnostic traces and browser checks. This does not establish physical sensor calibration or the motorcycle's oscillator frequency.

## Build the browser package

Activate Emscripten **4.0.23** on a build host with Python 3, Git, make, autoconf, flex and bison, then run:

```sh
python3 emulator/build_wasm.py --directory /tmp/xt660-wasm-core --jobs 4
python3 emulator/test_wasm.py
```

`dist/xt660-wasm` contains the runtime and a separate deterministic test executable. The latter is run in Node and compared with the recorded Windows reference. The browser runtime uses one worker and needs no SharedArrayBuffer or special cross-origin isolation headers. Sources, BIN hashes and runtime hashes are checked when packaging the website.

The [browser release](https://github.com/terrafirma2021/yamaha-xt660/releases/tag/emulator-browser-v0.1.0) contains a static package and complete corresponding sources. To rebuild its source archive, extract it and run the commands from `source/`, using `--directory ucsim`. To serve a new build locally:

```sh
python3 scripts/site_emulator.py --runtime dist/xt660-wasm --destination dist/browser-preview/emulator
python3 -m http.server 8767 --directory dist/browser-preview
```

Open `http://127.0.0.1:8767/emulator/`. The HTTP server only serves files. Browser and native builds remain separate options. The manually triggered [browser workflow](../.github/workflows/emulator-browser.yml) performs the build and execution comparison; normal Pages publishing only verifies and copies the committed runtime.

The browser speed improvements defer peripheral bookkeeping only between observable events and use direct instruction reads from the same flash backing memory. I/O accesses, interrupt delivery, flash-busy checks, RTI and COP deadlines retain their checks. Every CPU instruction still executes. Matched checkpoints include cycle counts, registers, RAM, storage, K-line replies and output-event signatures.

The uCsim-derived code is GPL-2.0-or-later; see [COPYING](COPYING). [Bundled dependency notices](browser/licenses) cover Emscripten, its runtime libraries and nlohmann/json. Source archives include the patched pinned uCsim tree, our core and browser code, build scripts and JSON header.

## Windows download

[Download the native Windows x64 package](https://github.com/terrafirma2021/yamaha-xt660/releases/tag/emulator-v0.1.0). Extract it and run **XT660.Emulator.exe**. Keep the extracted files together. Python, WSL and a compiler are not needed to run it.

The Windows process owns the MCU, peripherals, serial peer and simulation clock. Its worker runs independently of HTTP requests. The browser reads snapshots and sends input controls: closing, refreshing or backgrounding the tab does not pause the MCU. **Pause simulation** is an explicit command. Close the executable to stop the process.

Timing targets one simulated second per real second under the existing **nominal 16 MHz** profile. The worker sleeps when ahead and reports when behind; it never skips instructions to catch up. This is a functional MCU/peripheral emulator, not a physically timed engine or confirmed oscillator measurement. [Native validation](native-validation.json) records reference comparisons, headless timings and the tested executable hash.

Open **http://127.0.0.1:8766/**. Select an ECU, turn the key, leave Run on and press Start. No physical COM port is opened. Storage is retained across key cycles within a selected ECU; switching ECU creates a fresh fixture. Bench controls expose raw inputs, serial replies, step, trace and BIN integrity checks.

## Build the Windows package

On a Linux build host, install Git, Python 3, make, autoconf, flex, bison and the MinGW-w64 x64 POSIX compiler. Then:

```sh
python3 emulator/build_windows.py --directory /tmp/xt660-windows-core --jobs 4
```

This creates `dist/xt660-emulator-windows-x64.zip` and a complete corresponding-source archive. Dependencies and the uCsim commit are pinned; the C++ runtime is statically linked. To rebuild the release source archive, extract it and run the script from `source/`, with `--directory ucsim`.

The manually triggered [Windows workflow](../.github/workflows/emulator-windows.yml) builds on Linux and checks the executable on Windows. Pages publishing does not run this build.

Developer checks on Windows:

```powershell
python emulator/test_native.py --bundle dist/xt660-emulator-windows-x64
python emulator/test_emulator.py --ucsim dist/xt660-emulator-windows-x64/XT660.Core.exe
```

`XT660.Core.exe` retains the uCsim command-line debugger; `XT660.Emulator.Check.exe` runs deterministic headless checks. Neither is needed to operate the cockpit. Optional runtime arguments: `--port`, `--no-browser`, `--image ID` and `--storage fixture.bin` (512-byte external-storage fixture, with `--image`). The latter starts key-off and does not change authentication code.

The [Windows core regression](windows-core-validation.json) also covers instruction fixtures, breakpoints/watchpoints, ADC, GPIO, timers, watchdog, SCI, EEPROM, and execution of the boot programming routines. The local Windows pipe patch prevents the debugger from blocking when input is buffered. No upstream pull requests are submitted by this build.

## Reference Linux/Python harness

Linux/WSL needs Python 3, Git, make, g++, autoconf, bison, flex and ncurses development libraries. The build does not install system packages. From this repository:

```sh
python3 emulator/build.py --directory /root/xt660-ucsim
python3 emulator/dashboard.py --ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu
```

This older research harness is not used by the Windows package. To run it through WSL from PowerShell:

```powershell
python emulator/dashboard.py --wsl --ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu
```

Open **http://127.0.0.1:8766/**. Select an ECU, turn the key, leave the red run switch on and press Start. Key-on runs authentication only when enabled by that BIN. N/1 changes the external neutral input; the throttle changes its ADC input and the simplified rotating-engine fixture. Pause stops instruction batches; it does not turn the key off. Bench controls contain the raw inputs, serial transcript, step, trace and integrity checks. Switching ECU selects a fresh storage fixture; key cycles within a selected ECU retain its external storage in this server session.

The server binds only to loopback. It uses bundled HTML/CSS/JavaScript, a per-session request token and same-origin checks. It has no upload, arbitrary debugger-command or physical-port endpoint. Close it with Ctrl+C.

## What is being executed

- Startup and application instructions come from hash-checked source BINs. Normal engine runs leave every one of the 59,392 flash bytes unchanged.
- The storage defaults are produced by executing each BIN's own factory initializer in an isolated session. All five produce the same 512-byte fixture, SHA-256 `93f11ba1d85ba762b87ee17ba9e9434e1bb8c81d6df23b238892f94f77fb68f6`. This is not an EEPROM read from a motorcycle.
- A separate synthetic registration record supplies `ABC` three times and trailer `5AA5` at external-storage offsets `50–5A`. Authentication runs through actual SCI receive interrupts, main-loop calculations and replies. No runtime flags or authentication branches are patched. The supplied immo-off BIN correctly skips authentication.
- SCI1 exercises the challenge/response sequence and normal `FE` / `01` meter requests, with reply checksum checks. Corrupt authentication responses are tested separately.
- PT1 receives ten ordinary tooth intervals and one double interval per synthetic revolution. This follows the recovered gap detector, not a measured rotor trace. The firmware selects the /32 timer prescaler. Both families synchronise, generate PT3 coil and PT6 injector transitions, and detect pulse loss.

The dash consumes real five-byte replies, validated before display, through the native meter peer (`meter.py` in the reference harness). B0 is the engine code, B1 the received road-pulse delta, B2 the fault/status byte and B3 the coolant or diagnostic data. The normal frame contains no gear field: N/1 follows the neutral-switch fixture. Fault injection changes ADC inputs; the firmware qualifies and transmits the resulting fault. Received codes in the sidebar are session observations, separate from ECU history.

RPM is explicitly **nominal**, using B0 × 190 / 5.12 under the existing 16 MHz profile. Road speed is displayed as **pulses per reply**, not invented km/h. Coolant defaults to the exact received code. Optional `reply − 30 °C` remains a candidate with an unverified offset. The TEMP indicator compares the received code with 136; it is a dashboard threshold, not a read of the fan relay. Throttle percentage means control travel across the fixture's ADC range, not calibrated throttle angle.

The rotating-engine fixture ramps tooth intervals, supplies an intake-pressure ripple and models the fuel-relay supply feedback. It sustains rotation only after observing coil and injector outputs, and stops after sustained loss of either. The starter input is released before the first reset instruction; Start closes that external contact immediately. First gear supplies four road pulses per synthetic crank revolution solely as a demonstration fixture; this is **not a measured XT sensor/gear ratio**. These external signals enter the MCU model; no ECU runtime variables or flash bytes are patched. The model does not calculate combustion, torque, acceleration, wheel speed or physical temperatures.

The former 32-million-cycle pre-start wait was a host workaround, not a Yamaha requirement. It masked a fixture error: PB1 started low during reset, then was released after startup, creating a false starter cycle. In the early firmware, release arms `BF8:40` at `9019`; the capture path can then set `BF8:80` and reset synchronization at `DD0B–DD17`. Presenting the released contact from reset removes that false event. The [startup checks](startup-validation.json) cover immediate start across all five complete BINs, real output transitions, throttle control and rejection of an incorrect key. The ECU's debounce, authentication and inhibit code still executes.

In the reference Windows/WSL harness, validated HEX bytes are staged in a private Linux temporary file to avoid the debugger's character-by-character reads through `/mnt/c`. The file loader and firmware initialization still run. Dashboard polling adds no fixed delay when execution already exceeds the nominal simulated interval; this does not make the CPU core run in real time. Host latency measurements are recorded separately from simulated cycles.

The [recovered pressure calculations](../analysis/semantics/PRESSURE_ESTIMATE.md) run inside the original firmware. The external intake model supplies ADC1 with a pressure dip once per two crank revolutions: opening the throttle reduces the dip, increasing speed increases it, and stopping restores the selected ambient input. Its ambient count, waveform, phase and pumping coefficients are demonstration parameters, not recovered kPa calibration or a volumetric-efficiency map. The firmware still detects a disconnected pressure input and checks pressure variation. ADC4 follows the PA2 relay command; a separate PT5 input pulse acknowledges PT3 coil release through the actual timer-capture path. Neither supply nor ignition fault flags are forced clear.

**Enter diagnostics** performs key-off/key-on, holds SELECT + RESET for at least eight simulated seconds, releases them, then holds them for at least two seconds to confirm dIAG. It sends FE/CD/CA/CB/CC exchanges and waits for the firmware's replies; it never sets diagnostic RAM flags. These minimum holds follow the [Yamaha service manual, diagnostic procedure](https://www.manualslib.com/manual/1068449/Yamaha-Xt660r-2004.html?page=350#manual). The peer's 16 ms request spacing is a chosen simulation cadence under the nominal 16 MHz clock, not a measured motorcycle-meter cadence. Host execution may take longer than simulated time.

**Previous / Next** send released-button and press sequences. The ECU controls selection, skips and wraparound: 19 items in the early BIN and 20 in the later BIN. **Run test / Stop test** operate the simulated run switch. Coil, injector, PAIR and fuel-relay tests produce five pulses at one-second intervals; fan and headlight tests produce five cycles at five-second intervals. The warning lamp follows actual serial replies. PAIR is PP1 in the early application and PP0 in the later application.

**d:61 History** and **d:62 Count** navigate using the same button commands. Clear history in d:62 models the supply-monitor low/high transition used by the run-switch procedure. Actual EEPROM writes remain firmware operations; active faults can remain or recur. Later d:63 displays active O2 faults (24/31/32), not stored history. **Exit diagnostics** cycles the simulated key and reconnects in normal meter mode.

The cockpit art is a generated backdrop with a transparent top-down key asset. The key and lock slot turn together. The red rocker pivots in a fixed recess: press its upper end for Stop or its lower end for Run; keyboard activation toggles it. These visual angles are illustrative. Keyboard labels, focus outlines and reduced-motion support remain available. All assets are local. The R1-inspired artwork does not imply an R1 ECU or protocol. [Control appearance checks](cockpit-controls-validation.json) cover desktop/mobile layouts, themes and the existing ECU actions.

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

Tests write detailed logs under ignored `.runs/`. [validation.json](validation.json) records the integrated firmware and controller checks; [desktop-validation.json](desktop-validation.json) records the C# integration separately. [dashboard-validation.json](dashboard-validation.json) records the original browser checks; the [responsiveness follow-up](dashboard-responsiveness-validation.json) covers stable controls, startup, throttle percentages and diagnostic navigation. Each report identifies its tested source hashes. None is a hardware certificate.

Cockpit checks are separate from the shorter core regression:

```sh
python3 emulator/test_cockpit.py --ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu
python3 emulator/test_startup_sequence.py --ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu
python3 emulator/test_cockpit_faults.py --ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu
python3 emulator/test_pressure_faults.py --ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu
python3 emulator/test_diagnostics.py --image xt660-2004-2006-companion --ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu
python3 emulator/test_diagnostics.py --image xt660-2c1-10 --ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu
```

[cockpit-validation.json](cockpit-validation.json) records sustained idle/full-throttle/idle runs, controls and unchanged flash across the five complete BINs. [cockpit-fault-validation.json](cockpit-fault-validation.json) records active faults, history after a key cycle, d:61/d:62 communication and firmware-controlled EEPROM clearing in both families.

[pressure-fault-validation.json](pressure-fault-validation.json) checks healthy ripple, stuck pressure and disconnected pressure without disabling fault detection. Diagnostic reports for the [early](diagnostic-validation-xt660-2004-2006-companion.json) and [later](diagnostic-validation-xt660-2c1-10.json) BINs record both holds, every selectable item in both directions, actual output edges for all six actuator tests, warning replies, normal-mode exit and unchanged flash.

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
| `[35..38]` | Pending PT1 interval, PT2 road-pulse interval, continuous crank, road-pulse count |
| `[39]` | External intake-pressure ripple amplitude; zero disables |
| `[40]` | External ADC4 supply follows PA2 fuel-relay command; zero leaves it independent |
| `[41]` | External ignition-driver acknowledgement on PT5 after PT3 release |
| `eeprom[0..511]` | Persistent external-storage fixture bytes |

## Model boundaries

The conditional MCU reference is [MC9S12T64 Rev 1.1.1](https://www.nxp.com/docs/en/data-sheet/9S12T64AF16V1.pdf). The model covers the firmware-used 8N1 SCI paths, SPI master transfers and observed storage protocol, ADC sequencing/formatting, GPIO directions/latches, ECT compare/basic capture, RTI, PLL status, watchdog servicing and maskable interrupts. Disabled PWM counter/period/duty registers follow pages 347–350, including write-to-clear counters; later diagnostic entry accesses these without enabling PWM. Flash checks cover bank selection, sector erase, word programming, protection, errors and busy-bank access.

It is a functional model with instruction-boundary peripheral updates. PLL acquisition, storage busy and flash busy durations are deterministic fixtures. Exception-entry timing, analogue settling and oscillator frequency are not calibrated. Unsupported modes stop explicitly: banked CALL/RTC, advanced ECT buffering/pulse accumulators, external ADC triggering, SCI parity/9-bit/break and unused PWM modes. Watchdog reset requests stop with a reason rather than restarting the MCU. It is not a model of every silicon function or every physical fault.

The separate XT host application polls idle console input at 1 ms rather than 100 ms. This affects host responsiveness only; paused MCU time and instruction clocks do not advance.

Local core fixes cover decrement width, indexed addressing, flags, bit branches, MOV auto-index updates/disassembly, CCR X-mask transfers, loop decoding, ticks and step-over metadata. Builds pin µCsim commit `59a14ff99efe7e92474faf4c4ddf57b5e4ff0631`, verify known patch states and preserve unrecognised local edits. **No upstream submissions have been made.**

## License

The emulator and µCsim-derived patches use GPL-2.0-or-later; see [COPYING](COPYING). µCsim remains credited to its upstream authors. This does not assign a license to Yamaha firmware.
