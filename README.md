<div align="center">

<img src="MegaSerial/resources/app_icon.png" alt="MegaSerial" width="128" height="128" />

# MegaSerial

**A modern, cross-platform serial monitor for embedded development.**

Send and receive ASCII, HEX and binary data, save one-click command shortcuts,
plot live numeric data, and automate multi-step command sequences that advance
**by time, by response, or both**.

[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-2563eb)](#downloads)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776ab)](#run-from-source)
[![Built with PyQt6](https://img.shields.io/badge/UI-PyQt6-41cd52)](https://pypi.org/project/PyQt6/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Release](https://img.shields.io/github/v/release/MasoudHD/MegaSerial?display_name=tag)](../../releases/latest)

</div>

---

## Table of contents

- [Features](#features)
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

## Features

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
  time series or XY plot, with multiple auto-detected series.
- **Projects** – save and reload the full workspace (sequences, settings and
  captured logs) as a single `.msproj` file.
- **Full port control** – baud rate, data bits, parity, stop bits, RTS/CTS and
  XON/XOFF flow control, plus manual DTR / RTS toggles.
- **Auto-reconnect** – if the device drops or re-enumerates (common with cellular
  modems), the port is reopened and running sequences resume automatically.
- **Dark / Light / System** themes (system preference auto-detected on GNOME).
- **Persistent config** – settings, shortcuts, history and sequences are saved
  between sessions.

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
   timestamps, direction and autoscroll. Received data is shown live; sent data
   is echoed in the accent color.
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
  dialogs.py        # shortcut / step editors
  theme.py          # dark / light / system theming
  config.py         # JSON persistence
  utils.py          # ASCII / HEX / binary conversions
megaserial_entry.py # PyInstaller entry point
MegaSerial.spec     # PyInstaller build spec
build_executable.*  # per-OS build scripts
docs/               # CSV sequence guide
tests/              # end-to-end test
```

## Contributing

Contributions are welcome. Please:

1. Fork the repo and create a feature branch.
2. Keep changes focused and match the existing code style.
3. Run `python3 tests/e2e_test.py` before opening a pull request.
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
