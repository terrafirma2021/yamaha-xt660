# XT660 emulator

First stage: run the real BIN from reset to its application entry, with instruction-level debugging. **Engine operation is not emulated yet.**

The five registered images with populated boot code reach their own application entry (`0x5000` or `0x4800`). The four images with absent boot code are rejected; no donor bytes are inserted. Tests check both boot wait loops, all 2,048 cleared RAM bytes, and all 59,392 unchanged flash bytes per complete image. See [validation.json](validation.json).

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

## What the model covers

- CPU12 instruction execution, with 518 independent fixtures for the local fixes and related addressing modes.
- Reset-vector loading and execution of the unchanged boot instructions.
- PLL-lock status and ECT modulus-counter load, prescaling, countdown, expiry and write-one-to-clear flags.
- Storage for the configuration/GPIO writes made during boot; this does not simulate the external circuits.
- Stops on unimplemented register accesses and attempted CPU writes to flash. Debugger reads do not trigger peripheral side effects.

The MCU reference is the conditional MC9S12T64 identification used elsewhere in the repository. Register behaviour follows [MC9S12T64 Rev 1.1.1](https://www.nxp.com/docs/en/data-sheet/9S12T64AF16V1.pdf), CRG and ECT chapters (particularly pages 396–407). PLL acquisition uses a deterministic 64-tick fixture delay, not a measured lock time. The core's reported elapsed seconds and the motorcycle's absolute timing are not validated.

The generic HC12 page registers and inherited 6800 CIA/PIA devices are excluded from this target: they overlap T64 clock registers and application flash addresses.

## Remaining work

Continuing past entry currently stops on ATD control register `0x0082`, written at `0x5006` in the companion or `0x4806` in the later entry layout. Next: ADC conversion sequences and completion flags, interrupt delivery, watchdog and remaining timer channels, followed by crank-edge inputs and injector/ignition outputs. SCI traffic and flash programming need their own device models. A dashboard follows those running behaviours.

Reaching application entry does **not** mean the application checksum, authentication, engine scheduler or flashing protocol has been exercised. The rest of the CPU instruction set and its timing still need wider validation.

Core fixes stay under `patches/`: decrement width/disassembly, indexed addressing, bit-operation fetch order, loop decoding, tick accounting and step-over metadata. They are local integration fixes. **No upstream submissions have been made.** Any future submission must exclude XT660 firmware, profiles and application code.

## License

The native extension and the µCsim-derived patches use GPL-2.0-or-later; see [COPYING](COPYING). µCsim remains credited to its upstream authors. The Python harness files use the same license. This does not assign a license to the Yamaha firmware.
