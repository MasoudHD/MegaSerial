<div align="center">

<img src="MegaSerial/resources/app_icon.png" alt="MegaSerial" width="128" height="128" />

# MegaSerial 2.0.0

**A modern, cross-platform serial monitor for embedded development.**

Send and receive ASCII, HEX and binary data, save one-click command shortcuts,
route device messages into independent panels, plot live numeric data, and automate
multi-step command sequences that advance
**by time, by response, or both**.

[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-2563eb)](#downloads)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776ab)](#run-from-source)
[![Built with PyQt6](https://img.shields.io/badge/UI-PyQt6-41cd52)](https://pypi.org/project/PyQt6/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Release](https://img.shields.io/github/v/release/MasoudHD/MegaSerial?display_name=tag)](../../releases/latest)

</div>

---

## Table of contents

- [What’s new in 2.0.0](#whats-new-in-200)
- [Features](#features)
- [Panel View](#panel-view)
- [Downloads](#downloads)
- [Run from source](#run-from-source)
- [Build a standalone executable](#build-a-standalone-executable)
- [Usage](#usage)
- [Command sequences](#command-sequences)
- [Live graphing](#live-graphing)
- [Configuration](#configuration)
- [Project layout](#project-layout)
- [Contributing](#contributing)
- [License](#license)
- [Author](#author)

## What's new in 2.0.0

The following features were added since the **`v1.0.0`** tag:

- **Panel View:** switch from the normal monitor to a configurable matrix of
  independent monitors, with up to 10 rows and 10 columns and uneven row lengths.
  Route messages using `@PANEL:<id>|<payload>` and set titles from the device with
  `@PANEL_TITLE:<id>|<title>`; ordinary and unknown-destination data goes to General.
- **Automatic panels:** start with General and reveal panels as their data arrives,
  arranging them into a compact grid. A persistent, checkable **Windows** menu
  lets you show or hide panels without interrupting reception.
- **Arrange and resize:** drag panel headers to swap positions or move into empty
  cells, and drag dividers to resize panels and rows. Routing IDs remain stable.
  Arrangements and sizes are saved in the project.
- **Independent histories:** each panel retains 10,000 messages by default.
  Right-click → **Window settings…** to change its capacity, title, background,
  message/title colors, RX/TX icon colors, timestamp and line-number overrides,
  and received-counter visibility. Reset settings to defaults, clear one panel,
  or hide it through its context menu.
- **Scoped search:** apply the shared filter to All panels or selected panels;
  panels outside the scope remain unfiltered. Hidden panels continue retaining
  data and counting received messages.
- **Device protocol profiles:** a zMonitor preset supports its binary framing,
  channel mappings, title/style commands and ANSI colors. Configurable text and
  binary-delimited profiles, a packet preview and JSON profile import/export
  support other device formats. See the [protocol guide](docs/protocol-profiles.md).
- **Monitor improvements:** optional line numbers, shared zoom with `Ctrl` + `+` /
  `Ctrl` + `-` or `Ctrl` + mouse wheel, red RX and green TX direction icons by
  default, and scrolling that pauses following when you scroll upward and resumes
  at the bottom. Global autoscroll remains the master switch.
- **Sending improvements:** Up/Down send-history navigation, optional clear after
  sending, and custom line-ending suffixes shared by manual sends, shortcuts,
  resends and sequences.
- **Sequence controls:** loop a sequence a fixed number of times, until a matching
  response arrives, or until stopped. Enable or disable individual sequences in
  a group without deleting them.
- **Exports:** structured monitor CSV, optional panel metadata in Panel View CSV,
  and graph export as PNG or plotted-point CSV.
- **Projects:** show the active project name in the title bar, open `.msproj`
  files from the command line, and register a Windows file association. Projects
  now also restore panel layouts, settings, histories, counters and protocol profiles.
  Existing project files remain supported; the `.msproj` format version stays 1.
- **Reliability:** atomic, lock-guarded configuration writes for multiple instances,
  shared serial-payload conversion helpers, and expanded automated regression tests.
  A GSM module demo project is included in [`examples/`](examples/README.md).

Version 2.0.0 is the application version in this source tree. Downloadable binaries
are listed separately on the [Releases page](../../releases).

## Features

- **Panel View** – independent, configurable monitors with automatic discovery,
  device protocol profiles, scoped search and per-window settings. See below.
- **Serial console** with ASCII, HEX, Binary and Hexdump views, per-line
  timestamps, TX/RX direction markers, colored output and autoscroll.
- **Split view** – show the data stream in two side-by-side panes at once, each
  with its own format (e.g. ASCII on the left, HEX on the right).
- **Bytes per row** – for HEX / Binary / Hexdump views, choose 8 / 16 / 32 / 64
  bytes per line.
- **Zoom** – `Ctrl` `+` / `Ctrl` `-` or `Ctrl` + mouse wheel resize the monitor
  text; both split panes stay in step and the level is remembered.
- **Send** data as ASCII (with `\n \r \t \xHH` escapes), HEX (`48 65` / `0x48`)
  or binary (`01001000`), with a selectable line ending (default **CRLF**).
- **Custom line ending** – pick `Custom` to append any suffix you like, written
  with the same escapes (e.g. `\x1a` for Ctrl-Z). Works for manual sends,
  shortcuts, history resends and sequence steps alike.
- **Log export** – save the monitor as plain text, or as structured CSV
  (timestamp, elapsed time, direction, hex payload, log message) for analysis in
  Excel. See [docs/export-formats.md](docs/export-formats.md).
- **Shortcuts** – save frequently used commands and fire them with a double-click.
- **History** – every command you send manually is listed; double-click to reload
  it into the send bar, resend, or save it as a shortcut.
- **Command sequences** – build a list of steps that run top-to-bottom, each
  advancing *after a delay*, *on an expected response*, or *both*, with retries,
  failure detection and per-step beep-on-match. Import/export as CSV.
- **Sequence looping** – repeat a whole sequence a fixed number of times, until
  an expected reply arrives (ASCII/HEX/Binary), or forever until you stop it.
- **Sequence groups** – run several named sequences back to back; tick or untick
  each one to include or skip it in the group run without changing the sequence
  itself.
- **Live graphing** – plot numeric values parsed from the incoming stream as a
  time series or XY plot, with multiple auto-detected series. Save the plot as a
  PNG or export the plotted points as CSV.
- **Projects** – save and reload the full workspace (sequences, settings and
  captured logs) as a single `.msproj` file. The open project is shown in the
  window title, and a project can be passed on the command line or opened by
  double-click on Windows after a one-off
  [file-association registration](docs/file-association.md).
- **Full port control** – baud rate, data bits, parity, stop bits, RTS/CTS and
  XON/XOFF flow control, plus manual DTR / RTS toggles.
- **Auto-reconnect** – if the device drops or re-enumerates (common with cellular
  modems), the port is reopened and running sequences resume automatically.
- **Dark / Light / System** themes (system preference auto-detected on GNOME).
- **Persistent config** – settings, shortcuts, history and sequences are saved
  between sessions.

## Panel View

Choose **Panel View** above the monitor, then either **Configure panels…** for a
manual layout or enable **Automatic panels** to reveal destinations as messages
arrive. General uses routing ID `11`. IDs such as `32` originally address row 3,
column 2; use `3:10`, `10:2` or `10:10` when a coordinate is 10. Dragging a panel
changes its display position, never its routing ID.

With the MegaSerial protocol selected and **Line mode** enabled, send UTF-8 lines
terminated by LF or CRLF:

```text
@PANEL:32|GPS Fix acquired
@PANEL_TITLE:32|GPS Receiver
@PANEL:10:2|Temperature=42
```

Everything after the first `|` is payload, including further `|` characters.
Titles are optional. Ordinary RX, unassociated TX and unknown IDs fall back to
General without discarding their raw data.

Use **Panels ▾** beside the filter to choose its search scope, and **Windows ▾**
to show/hide panels. Right-click a header or log for **Window settings…**,
**Clear window**, **Hide window**, or **Reset arrangement**. Each panel has its
own scroll position and history capacity; busy panels do not evict quiet panels'
messages. Scroll upward to read history, then return to the bottom to follow new
messages. Hidden panels keep receiving data.

**Protocol: MegaSerial…** opens the profile editor for zMonitor or custom text/
binary-delimited formats. Panel configuration and protocol profiles belong to
`.msproj` projects. Normal Monitor and split monitoring remain available.

See the [Panel View guide](docs/panel-view.md) for layout, settings, history,
counters, search and export details, and the
[device protocol guide](docs/protocol-profiles.md) for framing and mapping examples.

## Downloads

Pre-built binaries for each release are on the
**[Releases page](../../releases/latest)** — no Python installation required.

| Platform | File | How to run |
|----------|------|------------|
| **Windows** (x64) | `MegaSerial-<version>-windows-x86_64.exe` | Double-click to launch. |
| **Linux** (Debian/Ubuntu/Mint, x64) | `MegaSerial-<version>-linux-x86_64` | `chmod +x` then run it. |

<details>
<summary>Linux: running the downloaded binary</summary>

```bash
chmod +x MegaSerial-*-linux-x86_64
./MegaSerial-*-linux-x86_64
```

To access serial ports your user must be in the `dialout` group:

```bash
sudo usermod -aG dialout "$USER"   # then log out and back in
```
</details>

<details>
<summary>Windows: serial port access</summary>

No extra permissions are required. If Windows SmartScreen warns about an
unrecognized publisher, choose **More info → Run anyway** (the binary is
unsigned).
</details>

## Run from source

Requires **Python 3.11+**.

```bash
# 1. Clone
git clone https://github.com/MasoudHD/MegaSerial.git
cd MegaSerial

# 2. Install dependencies
#    Debian / Ubuntu (recommended):
sudo apt install python3-pyqt6 python3-serial python3-pyqtgraph
#    …or via pip in a virtualenv (any OS):
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Run
python3 -m MegaSerial
```

On Linux you can also use the helper script:

```bash
./run.sh
```

## Build a standalone executable

The build scripts use [PyInstaller](https://pyinstaller.org/) to produce a
single self-contained binary that bundles Python and all dependencies.

**Linux** → produces `dist/MegaSerial`:

```bash
./build_executable.sh
```

**Windows** → produces `dist\MegaSerial.exe`:

```powershell
.\build_executable.ps1
```

> On Windows you can also just double-click `build_executable.bat`.

## Usage

1. **Connect** – pick a port (`⟳` refreshes the list), set the baud rate and
   framing, then click **Connect**.
2. **Monitor** – choose the view (ASCII / HEX / Binary / Hexdump) and toggle
   timestamps, direction and autoscroll. RX icons are red and TX icons green
   by default. Scroll upward to pause following, or back to the bottom to resume.
3. **Send** – type into the send bar, pick the format and line ending, then press
   Enter or **Send**. Click **★ Save** to store it as a shortcut.
4. **Shortcuts tab** – manage saved commands; double-click to send.
5. **Sequence tab** – **Add** steps, reorder with ↑/↓, then **▶ Run sequence**.

## Command sequences

A *sequence* is a list of steps that run top-to-bottom. For each step you choose
how it advances:

- **After delay** – wait a fixed time, then continue.
- **On response** – wait until an expected reply arrives (with timeout and
  *continue / stop / retry* behavior).
- **Response + delay** – wait for the reply, then also wait the delay.

Steps can beep on a match, fail fast on an error reply (e.g. `ERROR`), and the
whole sequence can loop. Sequences survive a reconnect, so a step waits for the
port to come back and resends rather than aborting.

Sequences import/export as **CSV**, so you can build them in a spreadsheet:

```csv
name,data,fmt,advance,delay_ms,expect,timeout_ms,on_timeout,beep_on_match,fail_on
Reset,AT+RST,ascii,response,500,OK,2000,retry,true,ERROR
Poll,52 45 41 44,hex,time,1000,,,,,
```

See the full column reference and examples in
**[docs/csv-sequence-guide.md](docs/csv-sequence-guide.md)**.

## Live graphing

Numeric values in the incoming stream (e.g. `temp=23.5, hum=40`) are parsed
automatically and can be plotted as a **time series** or **XY** plot with
multiple auto-detected series — handy for sensor telemetry.

## MegaSerial introduction on YouTube

<a href="https://www.youtube.com/watch?v=hnMM42_9xCU" target="_blank" rel="noopener noreferrer">
  <img src="https://img.youtube.com/vi/hnMM42_9xCU/0.jpg" alt="MegaSerial Tutorial: The Ultimate Open-Source Serial Monitor for Embedded">
</a>




## Testing without hardware

Create a virtual serial pair and talk to yourself (Linux):

```bash
socat -d -d pty,raw,echo=0 pty,raw,echo=0
# open one of the printed /dev/pts/N devices in MegaSerial
```

An automated end-to-end test lives in `tests/e2e_test.py`:

```bash
python3 tests/e2e_test.py
```

## Configuration

Settings, shortcuts, history and sequences persist between sessions in a JSON
file under your config directory:

- **Linux:** `~/.config/MegaSerial/config.json`
  (or `$XDG_CONFIG_HOME/MegaSerial/config.json`)
- **Windows:** `%USERPROFILE%\.config\MegaSerial\config.json`

## Project layout

```
MegaSerial/
  app.py            # QApplication entry point
  main_window.py    # UI + wiring
  serial_worker.py  # threaded serial I/O
  sequence.py       # sequence runner + response matching
  graph_panel.py    # live plotting pane
  data_parser.py    # numeric parsing for the graph
  project.py        # .msproj save/load
  event_history.py  # independent panel retention + chronological event index
  panel_view.py     # panel widgets, layout and menus
  panel_model.py    # project-owned panel definitions and settings
  panel_settings.py # per-window settings dialog
  panel_protocol.py # MegaSerial tagged-line parser
  protocol_profiles.py # streaming device protocol decoders
  dialogs.py        # shortcut / step editors
  theme.py          # dark / light / system theming
  config.py         # JSON persistence
  utils.py          # ASCII / HEX / binary conversions
megaserial_entry.py # PyInstaller entry point
MegaSerial.spec     # PyInstaller build spec
build_executable.*  # per-OS build scripts
docs/               # panel, protocol, export, sequence and architecture guides
tests/              # automated regression tests + hardware end-to-end test
```

## Contributing

Contributions are welcome. Please:

1. Fork the repo and create a feature branch.
2. Keep changes focused and match the existing code style.
3. Run `python3 -m unittest discover -s tests` and
   `python3 -m compileall MegaSerial tests`. Run `python3 tests/e2e_test.py`
   when the required serial test setup is available.
4. Open a pull request describing what changed and why.

## License

Released under the **MIT License**. See [LICENSE](LICENSE) for details.

## Author

**Masoud Heidari** — Embedded Systems Developer

- GitHub: [@MasoudHD](https://github.com/MasoudHD)
- LinkedIn: [heidarimasoud](https://www.linkedin.com/in/heidarimasoud/)
- Website: [masoud-heidari.com](https://masoud-heidari.com/)

If you find MegaSerial useful, you can support its development via
[Buy Me a Coffee](https://buymeacoffee.com/masoudhd) or
[Donito](https://donito.me/masoudheidari).
