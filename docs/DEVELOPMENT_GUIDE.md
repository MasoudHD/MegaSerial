# Development guide

## Prerequisites

- Python 3.11+
- Runtime packages from `requirements.txt`
- A serial device or virtual serial pair for integration testing
- Linux E2E testing additionally requires `socat`

Create a virtual environment and install the application dependencies:

```bash
python -m venv .venv
# PowerShell: .\.venv\Scripts\Activate.ps1
# POSIX: source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run from source:

```bash
python -m MegaSerial
```

On Linux, `./run.sh` is an equivalent launcher. Physical serial-port permissions may be needed (for example, membership of the `dialout` group on Linux).

## Verification

The available end-to-end test is:

```bash
python tests/e2e_test.py
```

It requires Linux `socat`, starts a virtual PTY pair, and exercises conversions, serial I/O, response matching, and a timed sequence. It is expected to be unavailable in a typical Windows-only environment. Before and after non-UI changes, also run a syntax check such as:

```bash
python -m compileall MegaSerial tests
```

For future changes, add focused automated tests alongside the modified behavior. Favor deterministic pure tests for `utils`, `data_parser`, `sequence` CSV/models, filtering, and project/config serialization. Do not make hardware access a prerequisite for ordinary tests.

## Build and release

- Windows: `build_executable.ps1` creates a dedicated build virtualenv, installs PyInstaller/Pillow, creates an `.ico`, and builds a one-file windowed executable under `dist/`.
- Linux: `build_executable.sh` uses `.buildvenv` and builds a one-file executable under `dist/`.
- CI: pushing a `v*` tag invokes `.github/workflows/release.yml`, which creates Windows and Linux artifacts and uploads them to the GitHub release.

Build scripts and CI currently duplicate PyInstaller options. If packaging behavior changes, update all relevant invocations or first complete the roadmap item that centralizes them.

## Safe development workflow

1. Read `AGENTS.md` and the relevant AS-IS sections of the architecture/debt documents.
2. Identify the smallest module boundary and existing tests affected by the requested change.
3. Make a small change that preserves serialized files, serial protocol behavior, and UI expectations unless a change is explicitly requested.
4. Add/update focused tests where practical, run the appropriate checks, and manually smoke-test UI/serial behavior when the change touches it.
5. Update user-facing docs, `DEFAULTS`, project migrations, and build configuration only when their behavior/schema changes.

## Prioritized migration/refactoring roadmap

### 1. Establish a repeatable safety net (first)

Add cross-platform tests for payload parsing/formatting, graph parsing, CSV round trips, filter rendering, project serialization, and sequence response outcomes. Add fixtures for legacy config/project data. This step changes no product behavior.

### 2. Define explicit persisted-data contracts

Document and test the settings, history, shortcut, monitor-event, and `.msproj` schemas. Reconcile missing defaults and stale CSV documentation. Add atomic writes and migration support only once tests preserve present behavior.

### 3. Extract an application/session controller

Move the event ingestion and sending/connection/runner lifecycle from `MainWindow` into one well-tested controller with narrow UI-facing signals/callbacks. Keep widgets and serial worker APIs intact.

### 4. Bound and formalize response buffering

After sequence tests exist, give `RxMonitor` a bounded response window or consume cursor while retaining correct matching across chunks and reconnects.

### 5. Simplify sequence execution threading

Separate the sequence state machine from the Qt thread wrapper. Make group execution compose the engine directly rather than invoking another `QThread.run()` manually.

### 6. Complete presentation/infrastructure separation

Gradually move remaining UI state/persistence wiring into services and consolidate build configuration. This is a series of small approved changes, not a rewrite.

## Critical compatibility notes

- Treat `.msproj` and user config as user data. Backward compatibility and error recovery are required for schema changes.
- Serial reconnection, DTR/RTS, flow control, and sequence timing are device-facing behavior; changes require device or virtual-port validation.
- The application is intentionally cross-platform, but the current test suite is not. Do not infer Windows behavior only from Linux E2E results.
