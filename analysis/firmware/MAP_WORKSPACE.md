# Map workspace and XDF export

The browser editor uses the loaded BIN's recovered map catalogue. Search by name, reference ID or address; filter by category or changed maps. Values and axis labels are raw. The map evidence link carries the current interpretation and scaling limitations.

Drag or Shift-click for rectangular selection; arrows move and Shift+arrows extend. Select-row, select-column and select-all controls provide shortcuts. Copy uses tab-separated text; paste accepts a rectangular block from its top-left cell. Paste and numeric edits reject out-of-range values instead of wrapping or silently clamping.

Set, add/subtract, multiply, row/column interpolation, smoothing, restore-original and paste all preview before applying. A committed block is one undo/redo operation. Interpolation uses increasing numeric raw-axis coordinates; step-range labels or unavailable coordinates use evenly spaced cell positions. Smoothing averages the original snapshot's available 3×3 neighbours within the selection, including its edges. Results round to the nearest integer. It is not a physical-unit-aware smoothing model.

Original and difference views are read-only. The linked 2D graph compares the selected row against the original; the rotatable 3D graph shows the edited/preview surface. Graph spacing uses cell positions, not physical-axis spacing. Original always means the file opened for this session, not an assumed factory calibration.

Known map-body edits can now be reopened after matching all other bytes against a registered reference, allowing supported feature patches and checksum compensation. Unknown code changes and edited axis storage remain inspection-only. Matching identifies the layout, not the historical source variant. The original is retained; the draft's startup checksum is corrected after edits and before saving.

**Export XDF** produces one XDF 1.70 file for all recovered maps in the loaded BIN. Addresses are file offsets with base offset zero, so the 59,392-byte and 65,536-byte files receive different definitions. Values are unsigned, big-endian, raw integers with identity conversion `X`. Axes are fixed raw labels. No speculative scaling, feature-patch definitions, checksum plugin or flashing protocol is included. External edits require startup checksum correction; reopening a recognised map-edited BIN in the browser performs that correction in its draft.

Validation: `node scripts/test_map_workspace.mjs` checks selection, editing, interpolation, smoothing, paste, bounds, identity matching and all 69,127 source cells. `python scripts/test_xdf_export.py` parses the exported XML independently and compares all 663 tables across nine BINs to their original bytes, dimensions, endian convention and file offsets. Browser checks cover editing, previews, undo/redo, comparison, filters, export and save/reopen. Native TunerPro import and ECU hardware behaviour are not verified by these tests.

Interaction references: [TunerPro table editing](https://tunerpro.net/WebHelp/source/tables.htm) and [table definitions](https://tunerpro.net/WebHelp/source/xdftableeditor.htm). The workspace implementation is original; it does not include TunerPro application code.
