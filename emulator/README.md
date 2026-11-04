# XT660 emulator

Run the real BIN from reset through startup and repeated main-loop entries, with adjustable ADC inputs and instruction-level debugging. **Engine operation is not emulated yet.**

The five complete BINs reach their own main loop without changing their firmware bytes. The runtime fixture has no crank pulses or serial peer, and SPI returns `FF` from a disconnected, pulled-high bus. This does not establish valid persistent settings, successful authentication or a running engine. Images with absent boot code are rejected; no donor bytes are inserted. See [validation.json](validation.json) for checks and their scope.

## Build and run

Linux or WSL, with Python 3, Git, GNU make, g++, autoconf, bison, flex and the ncurses development libraries. Building does not install system packages. From the repository root:

```sh
python3 emulator/build.py --directory /root/xt660-ucsim
python3 emulator/run.py --ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu
python3 emulator/test_emulator.py --ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu
```

Choose a build directory writable by your account; `/root/xt660-ucsim` is an example for a root WSL account. The build pins [µCsim 0.9.12](https://github.com/danieldrotos/ucsim/tree/ucsim-0.9.12), applies our local core fixes and links a separate XT660 target. Generated files stay in the chosen build directory and ignored `.runs/` folder.

On Windows, build using WSL. The launcher and checks can run from PowerShell:

```powershell
python emulator/run.py --wsl --ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu
```

Use `--image xt660-2c1-10` to select another registered image. Source hashes and image address offsets are checked before execution. This tool never connects to a motorcycle or writes a source BIN.

## Run the main loop

```powershell
python emulator/run.py --wsl --ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu --runtime --loops 1000 --image xt660-2c1-10
```

The bounded run starts at the hardware reset vector and stops after the requested number of main-loop entries. It reports ADC conversions, timer interrupts, watchdog services and SPI transfers. It only supplies external pin fixtures: PA5–7 high, PS4 high, eight ADC inputs at 512, and pulled-high SPI MISO. Other external inputs are low. `--adc` accepts eight replacement raw values; `--steps` sets an instruction limit. No application RAM flags, checksum code or authentication branches are patched.

The companion's main loop is `0x538B`; the other complete images use `0x4BC5`. The regression run checks 1,000 entries per image, periodic interrupt delivery, watchdog servicing and all 59,392 flash bytes after execution. Separate fixtures test timer compare/capture behaviour, SPI timing/queues, and watchdog timeout detection.

## Debugger

Add `--console` to open the debugger at reset. The launcher places a breakpoint at that image's application entry. Commands include:

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

Conditional breakpoints, read/write watchpoints, hit counts, instruction stepping and stepping over JSR are tested. Debugging is at assembly level. [µCsim command reference](https://www.ucsim.hu/cmd.html).

## Sensor routine demo

Run the selected BIN's unchanged ADC setup/read routines and print their RAM results:

```powershell
python emulator/run.py --wsl --ucsim /root/xt660-ucsim/src/sims/m68hc12.src/xt660-emu --sensors --image xt660-2c1-10 --adc 100 200 300 400 500 600 700 800
```

Inputs are eight raw ADC counts (`0..1023`), in channel order. Omit `--adc` for midscale inputs. The example stores `6400, 12800, …, 51200`: this firmware uses left-justified 10-bit results. It does not establish a temperature, pressure or throttle scale. The demo uses an isolated RAM/stack fixture; it does not run the application startup, EEPROM checks or engine loop.

The early companion executes `0x56D0` / `0x5728` and retains channels 6/7 in four RAM banks. The other complete images execute `0x4F31` / `0x4F52` and store those channels directly. Tests vary the inputs between calls and check every destination. The external analogue multiplexer circuit is not simulated.

In the debugger, `adc0=123` through `adc7=1023` change raw inputs. `info hardware xtboot` shows conversion counts, flags, last interrupt vector and fixture settings. GPIO fixtures are bytes in `xtboot_0_cfg`: offsets 9–14 supply PA, PB, PE, PT, PS and PP input levels; 15 supplies PK7 and 16 supplies PTAD. Offset 17 is the SPI receive-byte fixture (default 255); 18 selects external-byte mode (0) or test loopback (1). Output latches and direction registers determine GPIO reads. This represents driven digital levels, not ECU conditioning circuits. Timer-controlled PT outputs follow their compare configuration.

## What the model covers

- CPU12 instruction execution, with 518 independent fixtures for the local fixes and related addressing modes.
- Reset-vector loading and execution of the unchanged boot instructions.
- PLL-lock status, oscillator-relative periodic interrupts, and COP watchdog servicing. A watchdog reset request stops execution with its reason; reset-pin timing and re-entry are not simulated.
- ECT main-counter prescaling/overflow, compare actions, forced compares, channel-7 override/reset, basic edge capture, fast flag clearing, and the modulus counter.
- SPI master byte transfers, baud divisor, transmit queue, receive overrun and status/data acknowledgement. Its external fixture is explicitly disconnected; no EEPROM identity, contents or write persistence are invented.
- ADC sequence length, channel stepping/wrap, 8/10-bit results, signed/unsigned formatting, sample/convert delays, single/continuous operation, FIFO overwrite and documented flag clearing.
- Functional RTI, timer-channel/overflow, SPI, ADC-complete, modulus-counter and PLL-lock interrupt selection: enable/mask bits, HPRIO selection, CLI delay, register stacking and RTI restoration. Exception-entry bus timing and RTI tail chaining are not modelled.
- GPIO input levels, output latches and direction for the supported ports; boot configuration storage remains partial.
- Stops on unimplemented register accesses and attempted CPU writes to flash. Debugger reads do not trigger peripheral side effects.

The MCU reference is the conditional MC9S12T64 identification used elsewhere in the repository. Register behaviour follows [MC9S12T64 Rev 1.1.1](https://www.nxp.com/docs/en/data-sheet/9S12T64AF16V1.pdf), MEBI, CRG, ECT, SCI, SPI and ATD register chapters. CPU interrupt semantics follow the [CPU12 reference manual](https://mil.ufl.edu/4744/docs/hc12/cpu12rm.rev4.pdf), CLI/RTI and section 7.5. PLL acquisition uses a deterministic 64-tick fixture delay, not a measured lock time. ADC delays are measured in simulated bus cycles; analogue power-up settling and electrical errors are not modelled. Peripheral updates occur at instruction boundaries; prescaler changes and bus accesses are not cycle-accurate. The core's reported elapsed seconds and the motorcycle's absolute timing are not validated.

The generic HC12 page registers and inherited 6800 CIA/PIA devices are excluded from this target: they overlap T64 clock registers and application flash addresses.

## Remaining work

Next are crank-event sequences and the resulting ignition/injection behaviour, a persistent-storage device model, and actual SCI receive/transmit traffic. The current serial fixture is idle; transmission attempts stop rather than fabricate communication. Enhanced capture buffering, pulse accumulators, watchdog reset re-entry and precise exception timing also remain unfinished. A dashboard follows the measured firmware behaviours.

Startup and the main loop execute under the stated fixtures. This is not validation of every branch, fault, immobilizer exchange, map scale or physical actuator. The CPU instruction set still needs wider coverage. Unsupported register accesses and external ADC-trigger mode stop explicitly.

Core fixes stay under `patches/`: decrement width/disassembly, indexed addressing, bit-operation fetch order, loop decoding, tick accounting, ORCC dispatch and step-over metadata. The XT660 target also supplies maskable interrupt dispatch and correct RTI X-mask restoration. They are local integration fixes. **No upstream submissions have been made.** Any future submission must exclude XT660 firmware, profiles and application code.

## License

The native extension and the µCsim-derived patches use GPL-2.0-or-later; see [COPYING](COPYING). µCsim remains credited to its upstream authors. The Python harness files use the same license. This does not assign a license to the Yamaha firmware.
