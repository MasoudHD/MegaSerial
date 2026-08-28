# Incremental refactoring plan

## Guiding constraint

This is a reduction-of-risk plan, not an architecture replacement. Keep the current package layout and existing module boundaries unless a small extraction solves a demonstrated maintenance problem. Every step is intended to be independently commit-able and behavior-preserving.

## Step 1 — Create fast characterization tests for pure behavior

- **Problem:** The only current automated test requires Linux, `socat`, Qt, and serial I/O. Core behavior has no low-cost regression safety net.
- **Likely files:** add `tests/test_utils.py`, `tests/test_data_parser.py`, `tests/test_sequence_models.py`, `tests/test_project.py`, and `tests/test_monitor.py`; no application modules.
- **Change:** Add standard-library `unittest` tests for current behavior: payload parsing/formatting, line endings, CSV `Step` round trips (including `fail_on`), graph parsing, monitor filtering/rendering, and project event serialization. Use small in-memory or temporary-file fixtures.
- **Explicitly does not change:** Runtime code, UI, dependencies, project/config file format, build process, or the existing E2E test.
- **Tests that must exist before the change:** None; this step establishes them.
- **Acceptance criteria:** `python -m unittest discover -s tests` runs without hardware or `socat` on Windows/Linux; tests encode current behavior rather than desired future behavior; existing E2E test remains untouched.
- **Regression risk:** Low.
- **Dependencies:** None.

## Step 2 — Centralize payload construction

- **Problem:** Parsing a text payload and appending its line ending is repeated in manual send, shortcut send, history resend, and `Step.payload_bytes`.
- **Likely files:** `MegaSerial/utils.py`, `MegaSerial/sequence.py`, `MegaSerial/main_window.py`, `tests/test_utils.py`, `tests/test_sequence_models.py`.
- **Change:** Add one narrow `utils` helper that accepts text, format, and line-ending label and returns bytes. Replace only duplicate parse-plus-append expressions with that helper. Keep each caller’s surrounding policy (connection checks, echo, history recording, UI errors) where it is.
- **Explicitly does not change:** Accepted payload formats/escapes, line-ending labels, `Step` fields, sequence timing, send history policy, UI messages, or serial write behavior.
- **Tests that must exist before the change:** Step 1 coverage for every accepted format, invalid input, unknown/missing line-ending label, and existing `Step.payload_bytes` behavior.
- **Acceptance criteria:** All relevant send paths use the same helper; byte-for-byte outputs match pre-change tests; no new module, dependency, or public file format.
- **Regression risk:** Low.
- **Dependencies:** Step 1.

## Step 3 — Make persisted schemas explicit without changing their shape

- **Problem:** Settings and project payloads are untyped dictionary contracts split between `MainWindow`, `config.py`, and `project.py`; defaults already lag two UI settings.
- **Likely files:** `MegaSerial/config.py`, `MegaSerial/project.py`, `MegaSerial/main_window.py`, `docs/csv-sequence-guide.md`, `tests/test_project.py`, add `tests/test_config.py`.
- **Change:** Define schema constants/default keys in the existing persistence modules; add pure normalization/validation helpers that retain unknown settings and preserve current fallback semantics. Correct the CSV guide/header reference to include `fail_on`; add missing current default keys with their present effective defaults. Do not introduce dataclass hierarchies unless tests show simple functions are inadequate.
- **Explicitly does not change:** Config path, JSON layout, `.msproj` version/value, import/export UI, default user-visible behavior, or silent-failure policy. Atomic writes and user notifications are deferred.
- **Tests that must exist before the change:** Step 1 project round-trip fixtures plus fixtures for empty, malformed, partial, and legacy settings/project dictionaries.
- **Acceptance criteria:** Existing config and `.msproj` examples load to equivalent effective settings; unknown fields survive where they currently survive; documented CSV fields match `sequence.CSV_FIELDS`; no format version bump.
- **Regression risk:** Low–Medium.
- **Dependencies:** Step 1. Step 2 is not required.

## Step 4 — Bound `RxMonitor` safely

- **Problem:** Sequence response matching stores all historical RX bytes indefinitely, creating unbounded memory use and progressively larger searches.
- **Likely files:** `MegaSerial/sequence.py`, `tests/test_sequence_models.py` or new `tests/test_rx_monitor.py`; possibly `docs/ARCHITECTURE.md` and `docs/TECHNICAL_DEBT.md`.
- **Change:** Add a documented bounded response window/cursor strategy inside `RxMonitor`. Preserve matching of a response that arrives across serial chunks and begins after the mark made before a send.
- **Explicitly does not change:** Serial read behavior, monitor log retention, user-visible sequence settings, sequence CSV/project schema, or the send/reconnect policy.
- **Tests that must exist before the change:** Matches after a mark, non-matches before a mark, cross-chunk matches, expected-vs-fail pattern precedence, timeout/stop behavior, and long-stream bounded-memory behavior.
- **Acceptance criteria:** The buffer has a tested upper bound; all existing response semantics remain correct within the defined window; a long synthetic stream does not increase retained buffer size indefinitely.
- **Regression risk:** Medium.
- **Dependencies:** Step 1. Do not start until the exact matching-window semantics are agreed and tested.

## Step 5 — Extract monitor-event storage and filtering only if it remains hard to change

- **Problem:** `MainWindow` simultaneously creates events, owns their retention, filters them, controls rerendering, and feeds the graph. This is a cohesive responsibility but currently coupled to widgets.
- **Likely files:** add `MegaSerial/event_log.py` only if warranted; `MegaSerial/main_window.py`, `MegaSerial/monitor.py`, `tests/test_monitor.py`, possibly a new `tests/test_event_log.py`.
- **Change:** Move non-Qt event creation, bounded retention, and filtered iteration into a small focused helper. `MainWindow` retains widget updates, filter-control state, graph calls, and signal wiring.
- **Explicitly does not change:** Event dictionary fields, 6,000-event retention limit, regex behavior, rendering output, line-mode assembly, graph parsing, project export data, or UI layout.
- **Tests that must exist before the change:** Event ordering, bounded retention, filter direction/case behavior, filter changes followed by rerender, and project event round trips.
- **Acceptance criteria:** `MainWindow` delegates only storage/filtering; it does not gain a general state framework; monitor/project tests pass byte-for-byte/equivalently for retained events.
- **Regression risk:** Medium.
- **Dependencies:** Steps 1 and 3. Defer if monitor changes are infrequent.

## Step 6 — Isolate one connection/runner lifecycle section only when needed

- **Problem:** Connection setup/teardown and sequence runner lifecycle are interleaved with UI state transitions in `MainWindow`, making serial-related changes risky.
- **Likely files:** initially `MegaSerial/main_window.py`, `MegaSerial/serial_worker.py`, `MegaSerial/sequence.py`, appropriate new tests; add one focused helper module only after a concrete duplication/change need is identified.
- **Change:** Choose one scope, not both: either connection construction/lifecycle or runner construction/lifecycle. Move only non-widget policy into a narrowly named helper with callbacks/signals compatible with the existing UI.
- **Explicitly does not change:** `SerialWorker` thread model, auto-reconnect behavior, DTR/RTS behavior, sequence timing, widgets, or serial config/file format.
- **Tests that must exist before the change:** Mocked worker lifecycle tests for the selected scope, plus existing sequence response/cancellation characterization tests.
- **Acceptance criteria:** One focused responsibility has a testable owner; `MainWindow` remains the sole widget owner; no generic `AppController`, interface hierarchy, or wholesale signal rewrite is introduced.
- **Regression risk:** Medium–High.
- **Dependencies:** Steps 1 and 2; Step 4 for sequence-related scope. Postpone unless serial lifecycle work is planned.

## Step 7 — Simplify sequence threading only after production behavior is characterized

- **Problem:** `SequenceGroupRunner` directly invokes `SequenceRunner.run()`, which is functional but has non-obvious `QThread` ownership semantics.
- **Likely files:** `MegaSerial/sequence.py`, `MegaSerial/main_window.py`, `tests/test_sequence_models.py` or dedicated runner tests.
- **Change:** Extract a plain, cancellable sequence-execution function/internal object while keeping the current runner signal API as a wrapper. Change group composition only after tests prove timing, cancellation, retries, matching, logging, and progress behavior.
- **Explicitly does not change:** Step/project/CSV schema, UI labels, thread placement of serial I/O, retry semantics, timeout semantics, or reconnect resend behavior.
- **Tests that must exist before the change:** Deterministic tests for all advance modes, retry/continue/stop outcomes, failure matches, looping, stop during waits, group delay, group cancellation, and emitted signal/order behavior.
- **Acceptance criteria:** Group execution does not call another `QThread.run()` directly; all characterized sequence outcomes are unchanged; UI stays responsive under delays.
- **Regression risk:** High.
- **Dependencies:** Steps 1, 2, and 4. Do not begin until a serial/sequence change requires it.

## Debt deliberately deferred

Do **not** address these yet:

- **Full layer/package reorganization:** Current low-level modules already have usable boundaries. Moving everything into `presentation`, `domain`, etc. offers little near-term value and creates broad import and review churn.
- **Generic controllers, repositories, interfaces, or dependency injection:** There is no concrete interchangeability requirement. These abstractions would add indirection without reducing a present risk.
- **Typed models for every dictionary:** Start only at persistence/event boundaries if bugs or schema changes demand it. Converting shortcuts/history/UI settings wholesale is low-value churn.
- **Build-system consolidation:** It is duplicated but stable. It touches release delivery on both operating systems and should wait for a packaging change or a dedicated, testable build task.
- **Global pyqtgraph theme isolation:** Low-impact while the application has one plot context; address it only when graph/window behavior changes.
- **Broad exception cleanup:** Narrow exceptions adjacent to tested changes. A repo-wide cleanup risks turning recoverable device/OS failures into crashes.
- **Atomic config writes and user-facing persistence errors:** Valuable later, but they alter failure behavior and need agreed UX plus compatibility tests first.

## One recommended first refactoring task

After adding the narrow payload characterization tests from Step 1, perform **Step 2: centralize payload construction in `utils.py`**. It removes a real duplication across four send paths, introduces no new architecture or dependency, preserves all file formats, and has a low regression surface. Keep it to the single helper and direct call-site substitutions; do not combine it with send-policy or UI cleanup.
