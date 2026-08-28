# Technical debt register

Priorities are based on risk to reliability and future development, not a directive to rewrite the application.

| Priority | Debt / evidence | Risk | Incremental response |
| --- | --- | --- | --- |
| P0 | `MainWindow` is 1,506 lines and owns UI creation, state, connection lifecycle, event ingestion, filtering, sending, persistence, and sequence/group orchestration. | Changes are hard to isolate; regressions are likely. | Characterize behavior with tests, then extract a small controller/service by workflow. |
| P0 | `RxMonitor` retains every received byte for the process lifetime; unlike monitor events it has no cap or pruning strategy. | Long-running or high-rate sessions can exhaust memory; pattern matching cost grows with traffic. | Define response-window semantics, then cap/prune with tests for cross-boundary matching. |
| P1 | Automated testing is a single Linux/hardware-tool-dependent executable script. | Core parsing, projects, CSV, filters, reconnection policies, and UI orchestration can regress unnoticed; Windows development lacks a practical default test. | Add fast `unittest`/pytest-compatible unit tests for pure modules before refactoring. Retain E2E as optional integration coverage. |
| P1 | Persistence is loosely typed dictionaries merged silently with defaults; malformed JSON and write errors are silently ignored in `config.py`. | Corruption can be hidden, schemas drift, and users may lose configuration without feedback. | Add a validated settings model/schema and atomic save; report recoverable failures in UI/logging. |
| P1 | The project-file version is checked only for being newer. There is no migration mechanism or validation of nested settings/events. | Future changes can break `.msproj` compatibility or import partial invalid data. | Establish explicit migrations and fixture-based compatibility tests before schema evolution. |
| P1 | Sequence control uses nested `QThread` subclasses; `SequenceGroupRunner` creates a `SequenceRunner` then calls `runner.run()` directly rather than starting it. | Ownership/thread semantics are non-obvious and cancellation/signal behavior is fragile. | Write sequence timing/cancellation tests; later extract a plain execution engine with a single thread boundary. |
| P2 | Manual send, shortcut send, history resend, and sequence send repeat payload parsing, line-ending handling, connection checks, history/echo rules in several forms. | Inconsistent behavior becomes likely as features evolve. | Extract a tested send-command service while preserving each existing caller's policy. |
| P2 | Monitor events, shortcuts, history, settings, and projects are untyped dictionaries in UI code. | Misspelled/missing keys and serialization errors surface late. | Introduce dataclasses gradually at storage boundaries, with adapters for old dictionaries. |
| P2 | Documentation drift: `docs/csv-sequence-guide.md` calls the app “SerialTool” and its advertised full CSV header omits implemented `fail_on`; config defaults omit newer `show_line_numbers` and `clear_after_send` keys. | Users and future contributors receive incomplete schema guidance. | Correct documentation/default schema in a focused behavior-preserving change and add CSV/config tests. |
| P2 | Build configuration is duplicated among PyInstaller spec, OS scripts, and CI; console/window settings and collected assets vary. | Releases may differ by platform/path and changes require edits in several places. | Choose one canonical PyInstaller configuration, then make scripts/CI invoke it. |
| P3 | Broad exception handling is common in I/O, system integration, and configuration paths. | Genuine programming errors can be hidden and diagnosis is difficult. | Narrow exceptions as adjacent code is covered by tests; retain graceful device-failure handling. |
| P3 | `GraphPanel.apply_theme` changes pyqtgraph global configuration. | Multiple plots/windows or later components can have unexpected presentation coupling. | Isolate plotting configuration when graph behavior is next modified. |

## Duplicated or unclear responsibility hotspots

- Step-table operations occur in both `MainWindow` and `SequenceEditorDialog`; their UI implementation is deliberately similar but not shared.
- `MainWindow` constructs persistence dictionaries while `config.py` and `project.py` merely read/write them, leaving schema ownership unclear.
- `MainWindow` mixes persistent settings (`self.cfg`) with live widget state and models. The exact source of truth depends on the operation.
- Monitor formatting is correctly isolated in `monitor.py`, but event creation, filtering, retention, export, graph replay, and rendering decisions remain split across `MainWindow` and views.

## Non-debt observations

The low-level serial and sequence modules already avoid a direct UI dependency. Keep that seam: it is the most valuable base for incremental testing and extraction.
