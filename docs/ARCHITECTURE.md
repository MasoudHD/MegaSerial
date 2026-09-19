# Architecture

## AS-IS: current architecture

MegaSerial is a monolithic desktop application with a central `MainWindow` coordinator. It has useful functional boundaries, but UI construction, application state, workflow orchestration, and persistence coordination are co-located.

```text
app / __main__
      |
  MainWindow --------------------------------------------------------+
  |   |             |             |            |                   |
  | SerialWorker  MonitorView   GraphPanel   dialogs         config/project
  |   |             |             |                                |
  | pyserial       utils       data_parser                       JSON files
  |
  +-> RxMonitor <- SequenceRunner / SequenceGroupRunner <- Step models / CSV
```

### Dependency direction

- `app` depends on `main_window` and `icons`.
- `main_window` depends directly on nearly every feature module. It owns their instances and connects their Qt signals.
- `serial_worker` depends on pyserial and Qt only; it does not depend on UI modules.
- `sequence` depends on `utils` and Qt only; runners receive a write callable and `RxMonitor` rather than importing serial code.
- `monitor` depends on `utils`; `graph_panel` depends on `data_parser` and pyqtgraph.
- `dialogs` depend on `utils` and sequence models.
- `project` and `config` are independent JSON helpers, but schema composition is performed in `MainWindow`.

This direction is generally sound below the `MainWindow` layer. The main architectural issue is not circular imports; it is that the coordinator has accumulated too many responsibilities.

### Concurrency model

- Qt GUI widgets and `MainWindow` run on the application/UI thread.
- `SerialWorker` is a `QThread` with a blocking-ish read loop, synchronized writes, serial-open/reconnect ownership, and signals back to the UI.
- `SequenceRunner` and `SequenceGroupRunner` are `QThread` subclasses using Python events for cancellable waits.
- `RxMonitor` stores an unbounded byte buffer under a lock and lets runners wait for patterns. `MainWindow` feeds it immediately from serial RX.
- The donation widget starts a standard Python daemon thread for the optional remote config fetch, then returns data through a queued Qt signal.

### Key flows

1. At startup, `MainWindow` loads config, creates UI/state, then maps configuration into widgets.
2. Connecting constructs `SerialConfig`, starts `SerialWorker`, and routes its signals to `MainWindow` handlers.
3. RX bytes are added to `RxMonitor`, optionally assembled into text lines, then emitted as timestamped monitor events. Events are filtered/rendered, optionally graphed, and retained in a bounded `deque` of 6,000 entries.
4. A manual send, shortcut, or sequence parses user text with `utils`, appends a selected line ending, and writes to `SerialWorker`. Manual sends are echoed/logged and recorded in history; sequences log through their runner signal.
5. Shutdown stops runners and serial I/O, collects state from controls/models, and writes the JSON config.

## TO-BE: recommended target architecture

Keep the current small, flat module layout. Improve it only by extracting a cohesive responsibility from `MainWindow` when that responsibility has clear inputs, outputs, and tests. `MainWindow` should remain the Qt composition point; it does not need to become a thin shell or participate in a named architecture.

```text
MainWindow                 builds widgets and connects existing Qt signals
  ├─ serial_worker.py       owns serial I/O and reconnecting
  ├─ sequence.py            owns step models, matching, and sequence execution
  ├─ monitor.py             owns filtering/rendering for monitor views
  ├─ config.py/project.py   own file I/O and serialized format rules
  └─ small focused module   added only when a MainWindow responsibility is proven
```

The only likely extra modules are targeted helpers, not a framework:

| Candidate | Concrete reason to extract | Migration source |
| --- | --- | --- |
| A payload helper in `utils.py` | One canonical parse-plus-line-ending operation removes repeated send mechanics. | Manual send, shortcut/history resend, `Step.payload_bytes`. |
| A small persistence/schema helper | Config/project validation and migration become testable without UI widgets. | `MainWindow._collect_settings`, `config.py`, `project.py`. |
| A monitor-event helper | Event creation/retention/filtering becomes independently testable if this remains a source of complexity. | Monitor-related methods in `MainWindow`. |
| A connection/sequence coordinator | Only if the related `MainWindow` section remains difficult to change after test coverage exists. | Connection and runner lifecycle methods in `MainWindow`. |

Do not create a generic controller, repository, interface, or model layer pre-emptively. Extract only after a focused test suite establishes behavior, keep call sites stable where possible, and preserve file formats and Qt signal behavior at every step. The detailed sequence is in [INCREMENTAL_REFACTORING_PLAN.md](INCREMENTAL_REFACTORING_PLAN.md).

## Architectural decisions to preserve

- Use bytes, not text, at serial boundaries.
- Keep serial I/O off the GUI thread.
- Keep sequence code dependent on an injected send operation and RX monitor, rather than directly on pyserial.
- Preserve bundled fallback behavior for optional remote metadata.
- Keep persistence formats backward compatible or versioned/migrated.

## Panel View extension

Panel View is an additive presentation of the shared monitor event deque:

```text
SerialWorker → MainWindow.on_data_received → RxMonitor (unchanged raw bytes)
                      ↓ existing line assembly (Line mode only)
               PanelProtocolParser → optional metadata → shared events
                                                           ├→ MonitorView (raw)
                                                           ├→ GraphPanel (raw)
                                                           └→ PanelView → MonitorView (payload)
```

`panel_protocol.py` parses complete strict UTF-8 lines without Qt and provides a
nonmutating presentation projection. `panel_model.py` owns project layout,
validation, automatic row/column IDs, destination fallback, titles and search scope without Qt or event
storage. `panel_view.py` owns the configuration dialog, scope menu and layout of
compact reusable monitor widgets. `MainWindow` connects these to the existing
line pipeline, presentation switch, global options and project/export actions.
Raw mode never interprets panel commands. Sequence matching always receives the
original serial bytes before interpretation.

`project.py` accepts optional top-level panel workspace metadata without changing
format version 1. It is deliberately separate from global config. `monitor.py`
provides optional panel columns in its existing CSV exporter; normal CSV stays
compatible. See [Panel View](panel-view.md) for schema, protocol and limitations.

Panel workspace schema version 2 uses position IDs such as `32`. The pure
`migrate_panel_project` helper upgrades earlier custom-ID workspace metadata,
search scope and event routing during project load, preserving raw event bytes
and recording changed IDs in `original_panel_id`. No additional event store is used.
