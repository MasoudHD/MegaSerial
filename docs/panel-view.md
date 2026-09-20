# Panel View

Choose **Panel View** above the shared filter to replace the normal monitor with
independent log panels. **Configure panels…** edits rows, maximum columns, each
row's panel count and optional titles. IDs are generated automatically from the
one-based row and column: `11` is row 1, column 1; `32` is row 3, column 2.
IDs are read-only and always visible in panel headers. Create the layout and send
data immediately; titles and title commands are not required. Blank titles use
`Panel <ID>`. General occupies the first cell (`11`) and also accepts routed data.
Its title defaults to General and may be edited without affecting fallback routing.
Every row shares its width equally among its panels. Layouts support 1–8 rows
and 1–8 columns. Changing row lengths preserves titles and data by position ID,
not by flattened panel order. Removed positions fall back to cell 11; restoring
a position displays its retained events again.

Enable **Line mode** for routing. Send strict UTF-8 lines terminated by LF or CRLF:

```text
@PANEL:32|GPS Fix acquired
@PANEL:32|Latitude=32.654|Longitude=51.668
@PANEL_TITLE:32|GPS Receiver
```

Configured IDs are numeric strings derived from matrix positions. The parser
still accepts other string IDs, which fall back to General. Unicode payloads
and titles are supported. The first `|` separates the ID
from the payload; subsequent pipes and empty payloads are preserved. Invalid
UTF-8, control bytes (except tabs), malformed commands, and incomplete lines are
never interpreted as commands. Raw mode does not interpret the protocol. As with
any textual protocol, a binary stream that is byte-for-byte identical to a valid
UTF-8 command cannot be distinguished from that command; use raw mode for binary.

Potential commands remain buffered across the existing 150 ms idle flush until
LF arrives. Incomplete buffers exceeding 64 KiB are emitted as ordinary data;
the remainder of that logical line is not interpreted. Changing line mode or
closing the serial connection flushes incomplete commands as ordinary data.
Clearing the monitor also clears pending input. A still-pending incomplete line
is not yet a stored event and is not included in project/export output.

## Routing and search

General shows ordinary lines, old events, unassociated TX/log events and unknown
panel IDs. Unknown IDs do not expand the configured layout. Their original
`panel_id` is retained; configuring that ID later makes its retained events appear
in the corresponding panel. Title commands update configured panels immediately
and appear as a `Title: …` entry. Commands for unknown IDs are retained in General
but do not change its title; configure that panel's title manually or resend the
title command once it exists.

The existing **Filter**, regular expression, direction and ignore-case controls
are shared. The **Panels** menu selects which panels the filter applies to:

- **All** applies to every panel, including panels added later.
- Uncheck **All**, then check individual panels to filter just those panels.
- Panels outside the scope remain visible with their full retained content.
- No selected panels means no panels are filtered.

Invalid regexes use the normal monitor's behavior (no matching events), only
within the selected scope. The fallback panel determines the scope for unknown
IDs. Renaming titles preserves scope; removing positions removes those IDs
from an explicit scope. Search never changes session events.

Timestamps, delays, direction, line numbers, autoscroll, theme and Ctrl +/- or
Ctrl+wheel zoom reuse global monitor settings. Delays in a panel are relative to
its previous displayed event. Each panel has its own scrollbar. The normal
monitor, including split view, remains available and shows the original bytes.
Graphing and sequence response matching continue to receive their existing data.

## Projects and export

`.msproj` version 1 gains an optional top-level `panel_view` object:
`schema_version: 2`, `active`, `rows`, `max_columns`, `row_counts`, row-major
`panels` (`id`, `title`),
and `scope` (`null` means All). This is project state, not application config.
Missing or invalid panel configuration restores an inactive 1×1 General view.
Old events without routing remain valid and appear in General. Earlier Panel View
projects with custom IDs are migrated by matrix position on load: titles and
search scope are preserved, configured event IDs are mapped to position IDs, and
`original_panel_id` retains the old ID. Raw serial bytes are unchanged. Saving
writes panel schema version 2; the overall project format remains version 1.
Devices should use the new position IDs after migration.

The existing shared event deque remains the only event store (6,000 entries).
Parsed RX events retain original `data` bytes and gain `panel_id` plus either
`panel_payload` or `panel_title`. Panel rendering creates temporary projections;
normal rendering and graphing use the original event. A presentation-only cache
tracks rendered block counts to trim panels when the shared deque evicts events.

In Panel View, **Export CSV** uses the existing exporter and adds `panel_id` and
`panel_title` columns. The `text` column contains the panel payload/title message;
`data` remains the original bytes in hex. Existing timestamp, elapsed time, event
type and semantic RX/TX columns are preserved. CSV elapsed time remains relative
to the previous exported event. Unknown IDs retain their ID with an empty title.
Panel titles are the current configured titles at export time. General exports
as `11` / its current title. Unicode, quoting and newline escaping follow the normal
CSV exporter. Normal Monitor CSV retains its original columns and content.
**Save log** in Panel View writes the shown plain text grouped under panel headers.
Both exports respect scoped filtering.

## Manual review checklist

Automated offscreen tests cover routing, switching, search, layout editing,
project save/reopen, legacy reset, shared display options/zoom/theme, export,
rapid input and bounded retention. Before merge, verify on a desktop with a device:

- Monitor ↔ Panel switching, including a previously enabled split monitor.
- 1×1, multiple rows, and uneven rows such as 4/2/3; resize the window.
- Independent scrolling and autoscroll with long and wrapped lines.
- Live routed RX, title updates, General fallback, unknown IDs, and TX.
- All/one/multiple search scopes; unselected panels remain unfiltered.
- Timestamp and delay toggles, theme changes, Ctrl +/- and Ctrl+wheel zoom.
- Save/reopen a project, then open an old project without panel metadata.
- CSV/text export including Unicode and quoted content.
- Sustained rapid data across several panels, including the retention limit.

Desktop/device checks and Windows behavior are not established by offscreen tests.

## Other device formats

**Protocol: MegaSerial…** selects the existing text protocol, a ready-made
zMonitor preset, or guided custom text/frame profiles. Alternative profiles use
their own packet boundaries rather than Line mode. The zMonitor preset supports
channel mapping, title/style commands and ANSI colors. See the
[protocol profile guide](protocol-profiles.md) for setup, preview, file sharing,
metadata, export and framing limitations.

## Show or hide windows

In Panel View, **Windows ▾** lists every configured panel by position ID and title.
Uncheck a panel to hide it; check it to show it again. Other panels share the
available row width, and completely hidden rows collapse. IDs never change when
panels are hidden. The dropdown remains accessible when all panels are hidden.

Hidden panels continue receiving and retaining data under the existing shared
6,000-event limit. Showing a panel restores its retained content under the current
search filter. Visibility is independent of the search-scope **Panels** menu and
does not change routing or export contents. The Windows list follows title and
layout changes. New positions are visible by default.

An optional `hidden_ids` list in the project's `panel_view` metadata saves this
state. Older projects show all panels. Removing a position also removes its hidden
state; adding that position later shows it by default. No project format version
change is required. Manually check row resizing and all-hidden recovery on your
desktop before merge.
