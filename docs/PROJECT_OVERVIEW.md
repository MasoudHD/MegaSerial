# MegaSerial project overview

## Purpose

MegaSerial is a cross-platform desktop serial monitor for embedded-device work. It connects to a serial port, renders RX/TX traffic, sends ASCII/HEX/binary payloads, stores shortcuts and history, runs response-aware command sequences, plots numeric telemetry, and imports/exports workspace data.

The repository currently contains a Python 3.11+ application using PyQt6. The current release metadata identifies the application as version 2.0.0.

## Entry points and execution

| Entry point | Use |
| --- | --- |
| `python -m MegaSerial` | Normal source launch through `MegaSerial/__main__.py` and `app.main()` |
| `run.sh` | Linux source-launch wrapper |
| `megaserial_entry.py` | PyInstaller entry point |
| `build_executable.ps1` / `.bat` | Windows standalone build |
| `build_executable.sh` | Linux standalone build |
| `.github/workflows/release.yml` | Tagged-release build and upload workflow |

## Major components (AS-IS)

| Component | Responsibility |
| --- | --- |
| `app.py` | Creates `QApplication`, applies identity/icon, creates `MainWindow`. |
| `main_window.py` | Application coordinator and most UI: connection controls, event log, sending, persistence wiring, shortcuts/history, sequences, project import/export, filters, and graph integration. |
| `serial_worker.py` | `QThread`-based pyserial ownership, port discovery, read loop, writes, DTR/RTS controls, and automatic reconnection. |
| `sequence.py` | `Step`/`NamedSequence` models, CSV conversion, thread-safe RX matching, single/group sequence runners. |
| `monitor.py` | Monitor event filtering and per-view HTML rendering. |
| `graph_panel.py`, `data_parser.py` | Numeric-text parsing and pyqtgraph-based live plots. |
| `dialogs.py` | Editors for shortcuts, steps, and grouped sequences. |
| `config.py`, `project.py` | JSON persistence for user settings and `.msproj` workspace files. |
| `theme.py`, `icons.py`, `sound.py` | Presentation/system helpers. |
| `about.py`, `remote_config.py` | About/donation UI and optional remote metadata fallback. |

## Runtime data and data flow

```text
Serial device -> SerialWorker.data_received(bytes)
              -> MainWindow.on_data_received
              -> RxMonitor (raw bytes for response matching)
              -> line assembly -> monitor event deque -> MonitorView(s)
                                          |              -> GraphPanel
                                          -> project export / rendered log export

User send / shortcut / sequence -> utils.parse_input + line ending
                                -> MainWindow/SequenceRunner -> SerialWorker.write
                                -> optional TX event -> same monitor pipeline
```

`MainWindow` holds the live mutable application state: user configuration, monitor events, shortcuts, send history, the current sequence, sequence groups, serial worker, and active runners. It saves settings at shutdown and can package settings plus monitor events into a `.msproj` JSON file.

## Dependencies and external tools

Runtime Python dependencies are declared in `requirements.txt`:

- PyQt6 — desktop UI and threads/signals
- pyserial — serial-port access and enumeration
- pyqtgraph — live telemetry plotting

Build-only dependencies include PyInstaller and, on Windows, Pillow for `.ico` generation. The Linux end-to-end test additionally needs `socat` and a usable PyQt runtime. GitHub Actions builds Windows and Ubuntu 22.04 one-file executables.

The optional donation metadata request uses Python’s standard-library HTTP client to fetch a configured GitHub Gist; bundled `resources/app_config.json` is the fallback.

## Configuration and persisted files

- Per-user config: `~/.config/MegaSerial/config.json` by default, or `$XDG_CONFIG_HOME/MegaSerial/config.json`.
- Workspace/project: `.msproj` JSON files containing format version, project name, settings, and monitor events. `FORMAT_VERSION` is currently 1.
- Sequence exchange: CSV through `sequence.py`.
- Packaged resources: icon, about markdown, and fallback app metadata under `MegaSerial/resources/`.

## Tests

There is one executable test, `tests/e2e_test.py`. It checks payload conversions and a real `SerialWorker` + response-triggered `SequenceRunner` flow through a Linux `socat` virtual serial pair. It is not a normal cross-platform unit test suite and does not cover the UI, persistence, parsers, rendering, reconnection edge cases, or project/CSV compatibility.

## Assumptions and boundaries

- The repository provides no packaging metadata such as `pyproject.toml`, `setup.py`, or a pinned lock file; source execution is documented as the supported development path.
- The current working tree had no tracked modifications before this documentation was added.
- Hardware behavior and cross-platform serial semantics have been inferred from code and documentation, not exercised against a physical device during this review.
