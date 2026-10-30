# Dashboard speed output

The editor applies a **fixed integer pulse offset from −20 to +20 per dashboard reply**, as requested. This is not percent scaling, a km/h offset, or proportional sprocket compensation. Zero input always produces zero. Disabled output always produces zero. Otherwise the result is `min(255, max(0, captured_count + offset))`. Low nonzero counts can therefore become zero with a negative offset. The dashboard's speed and distance/trip accumulation may both be affected.

## Placement and memory

The Features panel now has two Enabled/Disabled rows. **Speedo disable: Enabled** selects zero output; Disabled allows the normal or offset-adjusted speed byte. **Speedo pulse offset: Enabled** applies the selected nonzero integer; Disabled restores offset zero. Changes to the number apply on commit while the offset is enabled. Zero means no adjustment, so its detected state is Disabled. The page may remember a previously entered amount for re-enabling, but radio states come from the BIN bytes. Both controls preserve the other setting, participate in undo/redo and automatic checksum correction, and remain unavailable for an unsupported BIN. The existing patch bytes and metadata format are unchanged.

| Family | Original load → store | Captured pulse byte | Outgoing speed byte | Reserved ROM patch block |
|---|---|---|---|---|
| Early | `6341 → 6344` | `0AE3` | `08A7` | `4FA6–4FBD` (24 bytes) |
| Late | `5B03 → 5B06` | `0B06` | `08A9` | `B100–B117` (24 bytes) |

These blocks are all `FF` in the nine registered source BINs. The early block lies within the 90-byte `4FA6–4FFF` padding before the application; the late block lies within `B0EC–B5FF` padding. Neither block overlaps decoded instructions, exported reference destinations, immediate address operands or any recovered map body. Known early reads closest to the block are the words at `4F9E` and `4FA0`. Absence of references is static evidence, not proof against every possible externally supplied pointer or unknown code path.

The patch replaces a three-byte `LDAA extended` with a three-byte `JSR extended`. File length and all other addresses stay fixed. A 14-byte routine saves CCR, reads the original captured byte, preserves stationary zero, adds the signed offset and uses carry to clamp the result. It restores CCR and returns A to the existing `STAA`. That store sets N/Z/V for the result and retains the original carry and interrupt masks. B, X and Y are untouched. Disabled output uses a five-byte routine. Version/settings metadata occupies six bytes at block offsets 16–21; the remaining bytes stay `FF`.

There is **no persistent RAM allocation, fractional state, startup patch or stack-pointer change**. The only extra stack usage is three bytes: the JSR return address and saved CCR. The original source pulse byte, physical pulse counter, ECU internal speed and gear calculations are unchanged. Enabled with offset zero restores the original instruction and all 24 padding bytes exactly.

## Frame construction and concurrency

The early pending-reply gate at `6299` calls `62AA`, clears pending bit `08AE:02`, then publishes ready bit `08AE:01`. The late equivalent is `5A5B → 5A6C`, using `08B0`. Thus the correction executes once per requested constructed reply. SCI1 reception is disabled while the reply is pending/transmitting; the transmitter checks ready before sending. A sensor interrupt can advance the physical counter without changing the captured byte used by this constructor. The patch introduces no shared mutable state or interrupt masking.

The ordinary reply checksum remains the existing code at early `6486–6492` / late `5C4B–5C57`; it includes the adjusted speed byte. The patch is not inserted into the separate immobilizer reply constructor or the boot protocol. Diagnostic selector 07's separate raw-value source is not patched. Speed bytes in replies using the shared application constructor receive the offset.

## Validation and limits

`python scripts/test_speed_patch.py` independently executes the actual emitted opcodes for 466,416 cases across all nine BINs. It covers all 256 input counts, all 41 offsets, enabled/disabled states, incoming carry states, stack/register/CCR preservation, the original reply checksum tail, and synthetic interrupt save/restore at each instruction boundary. The synthetic interrupt is not a full peripheral or timing simulation. Opcode/stack semantics were checked against the [NXP HCS12 core guide](https://www.nxp.com/docs/en/data-sheet/HCS12COREUG.pdf), including PSHC/PULC and extended JSR. There is no new division or multiplication.

`node scripts/test_speed_tools.mjs` checks all 738 settings, bounds/type rejection, map non-overlap, automatic startup checksum, exact restoration and undo, unchanged boot bytes, other-feature coexistence and re-import matching. A partially written patch, changed metadata or occupied patch block is rejected. The matcher still requires the rest of the BIN to match a registered reference, apart from supported feature changes and checksum compensation. Arbitrary map-edited imports remain inspection-only under the existing policy.

These are software/static checks, **not hardware qualification or approval to flash**. Live ECU flashing remains unavailable. Hardware evidence is still needed for dash interpretation, timing and real speed/distance behaviour. The original BINs and boot region are never rewritten by this editor operation.
