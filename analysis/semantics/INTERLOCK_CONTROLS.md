# Sidestand and lean-angle ECU controls

The [Tools page](https://terrafirma2021.github.io/yamaha-xt660/tools/index.html#tune) has separate Enabled/Disabled controls for **Sidestand ECU cut-off** and **Lean-angle cut-off**. These recipes are matched to the nine registered BINs and both application families. Enabled means the original firmware behaviour is restored; Disabled applies the bytes below to a draft with automatic startup-checksum correction.

Disabling these protections permits ECU operation with the stand down or after the motorcycle falls over. The tests establish selected software paths, not safe physical sensor removal or vehicle operation. The external starter-relay circuit, board wiring, existing latches and stored faults must not be confused with a BIN setting. No clutch control is added.

## Sidestand: inhibit flag and fault 19

| Item | Early application | Late application |
|---|---|---|
| Debounce routine | `CC30–CC62` | `C296–C2C8` |
| Inhibit assertion | `CC5E`: `1C 08 8C 80` | `C2C4`: `1C 08 8C 80` |
| Disabled assertion | Change opcode `1C` to `1D` (BSET → BCLR); keep operands | Same opcode change |
| Fault-19 configuration | `4E6C`: `00 → 80` | `4608`: `00 → 80` |
| Configuration copy | `5FFE` → RAM `0D57` | `570B` → RAM `0D8E` |
| Fault routine | `8B6F–8BEB` | `7F3F–7FBB` |

The debounce routine sets `088C:80` when its inhibit input has qualified. This is the sole direct BSET writer of that bit in each decoded application. The patch makes the qualified branch clear it instead; the normal permissive branch already clears it. Debounce timing and unrelated bits are retained. In an artificially seeded active state, clearing still waits for a qualification threshold; this is not a live RAM toggle.

Consumers include the normal injector gate (`F4AE` early, `F22A` late) and coil-charge gate (`EE9C` early, `E922` late). The patch changes their shared producer rather than removing each consumer or broadly disabling other cuts.

The separate configuration byte is required to bypass **new fault-19 detection and history creation**. Changing only the inhibit instruction would leave that diagnostic path active. Conversely, suppressing only fault 19 would leave the actual engine-inhibit flag active. Both bytes must match the supported recipe before the UI shows Disabled; a partial patch is unavailable.

Existing fault history is preserved. Diagnostic switch readings are not falsified, and unrelated fault/cut logic is unchanged.

## Lean angle: tip-over detection and disconnected-sensor fault

| Item | Early application | Late application |
|---|---|---|
| Master setting | `4E91`: `00 → 80` | `462D`: `00 → 80` |
| Tip-over path | `A8EA–A98F` | `9BAF–9C54` |
| Sensor-circuit fault-41 path | `BDFE–BE89` | `B7C9–B854` |
| Raw sample RAM | `08DD` | `08E3` |

The master setting is checked by both paths. With `80`, tip-over processing jumps to the existing clear path for `0884:02` and `0885:80`. It does not qualify a new overturned state or create a new fault 30. The fault-41 path takes its existing current-fault clear branch, clearing `08B1:10` early or `08B3:10` late and marking that current-fault record for update. It does not add a new history flag for an unplugged or out-of-range sensor.

This is a direct master setting, not a guessed ADC value or a replacement sensor curve. Enabling restores `00` and the original detection paths. The original sensor samples and diagnostic values remain available.

### Existing latches and fault history

The tip-over clear path only clears `0884:01` when `0881:20` is clear. A previously latched state can therefore survive a single call with the master disabled. Existing fault 30 can also remain in the stored/current bitmap, and its consumers can still inhibit operation. The patch does not erase persistent history or bypass all inhibit consumers. Fault 41's current bit is actively cleared in its ordinary eligible processing path; its history bit is retained.

The tool cannot claim that unplugging a sensor on an already-faulted ECU will immediately restore operation. It edits a BIN; it does not reset live RAM, erase history or operate the starter relay.

## External starting circuit and physical removal

The manufacturer's [2004 XT660R/X service manual, printed page 8-18](https://www.manualslib.com/manual/1068449/Yamaha-Xt660r-2004.html?page=400) describes starter permission through a relay circuit: neutral, or clutch pulled with the sidestand up. If neither condition is met, that circuit interrupts starter current. This establishes why an ECU-side sidestand patch alone cannot guarantee cranking after switches are disconnected. The manual's early-model wiring must not be assumed identical for every later harness.

The [connector-route audit](CONNECTOR_ROUTE_AUDIT.md) also leaves the exact interlock wire-to-MCU pairing unresolved because the relay/diode paths overlap. No bridge wire, connector cavity or physical removal procedure is inferred from these software patches.

## Reproduction

`python scripts/test_interlock_features.py` byte-checks the relevant disassembly against all nine BINs and executes 25,344 selected-path cases. It tests both sidestand input levels, both initial inhibit states, all 256 counter values, enabled and disabled instructions, fault-19 suppression, all 256 lean sensor bytes, active/stopped latch conditions and fault-41 clearing. Positive controls demonstrate that the original paths can create fault 19, trip the lean-angle inhibit and create fault 41.

`node scripts/test_tools.mjs` checks detected feature states, both directions of editing, partial-patch rejection, exact changed-byte sets, automatic checksum correction, original/boot preservation and re-import matching. It does not validate a physical motorcycle, external relay or wiring modification.
