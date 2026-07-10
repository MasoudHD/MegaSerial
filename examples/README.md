# MegaSerial examples

Sample project files you can import into MegaSerial to explore features without
building everything from scratch.

## Files

| File | Description |
|------|-------------|
| [`GSM_Module_Demo.msproj`](GSM_Module_Demo.msproj) | GSM/cellular modem workflow using AT commands, sequence groups, shortcuts, split view, and live graphing |

## Quick start

1. Launch MegaSerial (from a [release](../../releases/latest) or [source](../README.md#run-from-source)).
2. Click **Import project** in the toolbar.
3. Choose `GSM_Module_Demo.msproj` from this folder.
4. Explore the loaded workspace — you do not need hardware connected to inspect sequences, shortcuts, and the sample log.

To run against a real module:

1. Connect your GSM modem over USB serial.
2. Select the port and click **Connect** (the demo expects **115200** baud, 8N1).
3. Open the **Sequence Group** tab and click **▶ Run group**.

## What the GSM demo includes

### Sequence Group (main demo)

Three sequences run in order, with a 2 s pause between each:

1. **Module initialization** — ping the modem (`AT`), disable echo, enable verbose errors, wait for boot, check SIM ready (`AT+CPIN?`). Uses response matching, retries, beep-on-match, and fail-fast on `ERROR`.
2. **Signal and network** — query signal quality, registration, GPRS attach, and operator info. Includes a step that sends `AT+CPS` as **HEX** bytes.
3. **SMS configuration** — set text mode and new-message indications, list unread messages. The **Send SMS** step is **disabled** — enable it locally only after you replace the placeholder number.

### Sequence tab

A shorter 4-step health check (`AT` → `ATE0` → `AT+CSQ` → `AT+CREG?`) showing the same advance modes on a single sequence.

### Other loaded settings

- **Shortcuts** — common AT commands ready to double-click and send.
- **History** — sample manual sends.
- **Monitor** — a captured TX/RX log (simulated session) so you can see timestamps, direction markers, and split ASCII/HEX view.
- **Graph** — enabled; the sample log includes `rssi=` and `reg=` lines for live plotting.
- **Auto-reconnect** — on (useful when cellular modems re-enumerate after reset).

## No sensitive data

This demo is safe to share and commit to version control:

- No PIN codes, APN credentials, or IMEI numbers
- No real phone numbers (the SMS step uses a placeholder and stays disabled)
- Generic AT commands only

Edit steps locally before running anything that sends SMS or connects to a carrier network.

## Customizing

After import you can:

- **Edit** any step in the Sequence or Sequence Group tabs (double-click a row or use **Edit**).
- **Export CSV** from a sequence to see the exact column format, then re-import after editing in a spreadsheet. See [docs/csv-sequence-guide.md](../docs/csv-sequence-guide.md).
- **Save project** to write your changes back to a new `.msproj` file.

## Learn more

- [Command sequences](../README.md#command-sequences) — advance modes, retries, looping
- [CSV sequence guide](../docs/csv-sequence-guide.md) — full column reference for import/export
- [Usage](../README.md#usage) — connect, monitor, send, shortcuts
