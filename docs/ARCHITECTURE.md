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
3. RX bytes are added to `RxMonitor`, optionally assembled into text lines, then emitted as timestamped monitor events. Events are filtered/rendered, optionally graphed, and retained by `EventHistory` with independent per-panel capacities (10,000 events each by default).
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

Panel View is an additive presentation of the chronological monitor event index:

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

## Device protocol profiles

The project-owned panel workspace optionally contains a versioned protocol
profile. The default MegaSerial path retains the existing line assembly and
parser. Selected zMonitor/custom profiles use `ProtocolDecoder` in
`protocol_profiles.py` instead of that line assembler, after raw RX has already
fed `RxMonitor`. This is alternate framing in the same RX/event pipeline, not a
second serial reader or event store. The decoder retains only an incomplete
packet; returned records preserve raw bytes and add channel/destination metadata.

`protocol_dialog.py` validates profiles and provides channel mapping, import/export
and an isolated preview. `ansi_text.py` supplies escaped SGR rendering and plain
text projection. `PanelView` applies decoded title/style commands, while the
chronological event index still retains their raw frames. `MainWindow` coordinates
selection, bounded decoder flushing and event ingestion. No new runtime
dependencies are introduced. See [protocol profiles](protocol-profiles.md).

Panel View uses a vertical `QSplitter` for rows and a horizontal `QSplitter`
within each row. Dragged proportions live in optional `PanelWorkspace` fields
and use the existing project serialization path; resizing does not alter events.

Automatic panels use the same 100 bounded position IDs from `panel_positions.py`.
`PanelWorkspace` tracks discovered IDs and a manual-layout snapshot as optional
project state. `MainWindow` passes events to discovery before display filtering;
`PanelView` compacts existing monitor widgets into splitters without recreating
content or adding event storage. Protocol mapping validation shares the position
ID rules, including colon-separated coordinates when either coordinate is 10.

Panel drag-and-drop is confined to `panel_drag.py` (header gestures, same-view
validation and drop highlighting), `panel_arrangement.py` (bounded placement,
swapping and discovery placement), and `PanelView` (reparenting existing monitors).
Optional workspace `display_positions` separates display coordinates from routing
IDs. Moving does not replay or mutate events. Empty cells are drop targets within
the existing splitter layout; no dashboard framework or separate log store is used.

`event_history.py` owns independent destination queues and a chronological index
of the same event objects. `MainWindow` configures capacities from the workspace
and trims the affected panel presentation on eviction. Project saving and panel
export iterate the complete retained index; Normal Monitor remains a 6,000-event
presentation. `panel_settings.py` provides the extensible per-window settings dialog.
Capacity changes rebuild retention and replay views without altering serial I/O.

`panel_appearance.py` validates optional per-panel appearance and derives rendering
options without mutating global options or events. `panel_settings.py` exposes
color presets/pickers and display inheritance controls. The existing monitor
renderer accepts optional direction-icon colors; Normal Monitor keeps its defaults.
RX counters are workspace statistics incremented once at event ingestion, separately
from retained history, and persisted with the workspace. Clear-window requests go
through a `PanelView` signal to `MainWindow`, which clears only the destination
queue and its panel presentation, then updates normal views and graph replay.

`MonitorView` captures scrollbar position and whether it was at the bottom before
appending or replaying events. It follows only when already at the bottom and
global autoscroll is enabled. Panel replay and destination eviction preserve this
state across clear/trim operations. Window-title editing reuses existing workspace
titles; resetting settings changes dialog fields until accepted and needs no new
persistence fields.
