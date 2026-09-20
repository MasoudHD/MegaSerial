# Device protocol profiles

In **Panel View**, click **Protocol: MegaSerial…** to select a device protocol.
The existing MegaSerial protocol remains the default. Profiles affect RX packet
assembly in either monitor presentation; TX and sequence response matching still
use original bytes. No new connection, service, or dependency is required.

## zMonitor preset

Choose **zMonitor**, leave **Use zMonitor's default 4 × 4 layout** checked, then
click **OK**. The suggested layout preserves titles/styles at existing positions.
Uncheck the layout option if you want to keep your current matrix instead.

The wire format is:

```text
C8 <channel byte> <UTF-8 text payload> FA
channel byte = C9 + channel number (0–15)
```

There is no required newline. The default mapping is row-major: channel 0 → 11,
1 → 12, 4 → 21, 9 → 32, 15 → 44. The **Channel mapping** tab can map each device
channel to another panel position. Enter decoded channel numbers (`9`), not the
wire byte (`D2`). Multiple channels may target the same panel; one channel has
one destination. An unmapped channel or a destination absent from the layout is
shown in General (cell 11), retaining its device channel in event metadata.

Example Arduino transmission to row 3, column 2:

```cpp
Serial.write((uint8_t)0xC8);
Serial.write((uint8_t)0xD2);
Serial.print("Hello from zMonitor firmware");
Serial.write((uint8_t)0xFA);
```

Inside the same envelope, these case-insensitive commands update a configured
panel without adding their command text to its log:

```text
#TITLE:GPS Receiver
#TITLE_COLOR:#ffffff
#TITLE_BGCOLOR:0,80,0
#TITLE_STYLE:title=GPS Receiver;color=white;bg=#005000
#TITLE_STYLE:{"title":"GPS Receiver","color":"white","background":"#005000"}
```

Color values accept Qt color names, hex colors, or decimal `r,g,b`. Invalid
colors are ignored and recorded in the event diagnostic. The raw command frame
remains in the shared session event store and the normal monitor. Commands for
unconfigured destinations are shown in General and do not style General.
Configured title commands are omitted from Panel View's visible-log exports.
Project files still retain them. Current title colors survive project reopening
and layout edits.

ANSI SGR foreground/background colors (standard, bright, 256-color and RGB),
bold and reset are supported inside panel payloads. Each packet starts with the
default style. Text is HTML-escaped before rendering; payloads cannot inject HTML.
Search and Panel CSV use plain text without SGR sequences; original serial bytes
remain available in event data and CSV's hex `data` column. This is color support,
not terminal emulation: cursor movement and screen-clear commands are unsupported.

## Custom text line

Choose **Custom text line** and specify:

- A literal text prefix, which may be empty.
- A channel/payload separator; the first occurrence separates the fields.
- LF, CRLF, CR, or a custom hex line ending of 1–8 bytes.
- UTF-8, ASCII or Latin-1 payload encoding, with optional ANSI colors.

For example, prefix `$`, separator `:`, ending `0D 0A`, and mapping `gps → 32`
accepts `$gps:Hello:world\r\n` and displays `Hello:world` in panel 32. Position
channels such as `32` route directly to that position unless explicitly remapped.
Custom profiles do not interpret MegaSerial or zMonitor title commands.

## Custom delimited frame

Choose **Custom delimited frame**, then enter start and end delimiters in hex.
Each delimiter may contain 1–8 bytes. By default, the first byte after the start
marker is the channel number and payload begins immediately after that byte.
The default channel subtraction is zero.

Expand **Advanced header offsets** to set the zero-based channel byte index and
payload byte index, both relative to the byte immediately after the start marker.
The payload must begin after the channel byte. Set a decimal subtraction value
when the wire channel is biased (zMonitor uses 201, hexadecimal C9). Mapping keys
are decimal decoded channel numbers. Header bytes before/between these positions
are retained in raw data but not displayed as payload text.

No escape rules, checksums, variable-width channels, length-prefixed frames,
compressed data or arbitrary binary payload rendering are provided by this editor.
Start/end markers cannot occur in a frame's text payload. A new start marker
resynchronizes an interrupted frame. These constraints also apply to the zMonitor
preset; it uses the source project's unescaped delimiters. There is no automatic
protocol detection.

## Test before applying

The **Test packet** tab accepts hex bytes or text with escapes (`\n`, `\r`,
`\xNN`). **Use latest RX event** copies the latest stored RX bytes as hex. It does
not start another capture pipeline or consume serial data. Text input is encoded
as UTF-8; use hex/byte escapes for other encodings.

The preview shows recognized/unrecognized status, device channel, destination,
payload, control fields and framing diagnostics. A partial packet is reported as
incomplete. Preview does not modify live settings, events or panel titles. It
shows up to 20 packets from a sample of at most 64 KiB. Color validity is checked
when commands are applied to live panels.

**Import profile…** and **Export profile…** share validated JSON profiles. These
contain decoding rules and channel mappings, not session data or layout. Choose
**OK** to apply edits; Cancel leaves the live configuration unchanged.

## Retention, switching and persistence

Custom and zMonitor profiles own their framing and operate independently of the
Line mode checkbox, which is disabled while they are selected. Returning to the
MegaSerial profile restores that control and its previous value. The existing
MegaSerial line parser and raw-mode behavior are unchanged.

Profiles buffer only incomplete packets, up to 64 KiB. Noise, malformed packets,
invalid text encodings and oversized input are preserved as ordinary RX events
with diagnostics. Incomplete bytes are flushed as ordinary events on a profile
change or serial disconnect. Clear intentionally discards pending input. Opening
a project replaces the session, including pending input. A still-incomplete
packet is not yet a stored event and is excluded from save/export until flushed.

Changing a channel map affects future packets. Stored events keep their recorded
destination, original bytes, protocol and device channel. Removing a destination
from the layout displays its events in General; restoring it replays them there.

The profile is an optional `protocol_profile` field inside the project's
`panel_view` object, with its own `version: 1`. Existing project format version 1
and panel schema version 2 are unchanged. Missing or invalid profiles default to
MegaSerial; valid layouts and events remain available. Profiles are project-owned,
not global application config.

Decoded events add `protocol`, `device_channel`, `panel_id`, `panel_payload` and,
when relevant, `panel_ansi`, `panel_style`, `panel_control` or
`protocol_diagnostic`. Panel CSV appends `device_channel`, `protocol` and
`protocol_diagnostic` after its panel columns. Normal Monitor CSV remains unchanged.
The protocol button's tooltip shows the latest received diagnostic.

## Manual verification

Before merge, test on a desktop with real zMonitor firmware: preset selection,
4×4 mapping, custom mapping, title/style commands, ANSI colors, fragmented and
rapid RX, profile import/export, project reopening, and returning to the existing
MegaSerial protocol. Offscreen and virtual-port tests do not establish physical
device or Windows UI behavior.
