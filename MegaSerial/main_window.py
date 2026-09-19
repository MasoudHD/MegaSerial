"""Main application window wiring together connection, monitor, send,
shortcuts and the sequence runner."""
from __future__ import annotations

import json
from copy import deepcopy
from collections import deque
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QGroupBox, QLabel, QComboBox, QPushButton, QCheckBox, QLineEdit,
    QSplitter, QTabWidget, QListWidget, QListWidgetItem, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar, QSpinBox, QFileDialog,
    QMessageBox, QAbstractItemView, QSizePolicy, QStackedWidget,
)

from . import config, theme, utils, sound, __app_name__, __version__
from .serial_worker import SerialWorker, SerialConfig, available_ports, port_hwid
from .sequence import (
    Step, NamedSequence, SequenceRunner, SequenceGroupRunner, RxMonitor,
    ADVANCE_LABELS, LOOP_FOREVER, loop_from_settings, steps_to_csv, steps_from_csv,
)
from .about import AboutDialog, DonationDialog
from .dialogs import (
    ShortcutDialog, StepDialog, SequenceEditorDialog, SequenceLoopControls,
)
from .monitor import (
    MonitorView, compile_filter, event_matches_filter, clamp_font_point_size,
    write_events_csv, DEFAULT_FONT_POINT_SIZE,
)
from .panel_protocol import PanelProtocolParser, panel_event
from .panel_model import PanelWorkspace
from .panel_view import PanelView
from .graph_panel import GraphPanel
from .icons import app_logo_pixmap
from . import project as project_io

BAUD_RATES = ["300", "1200", "2400", "4800", "9600", "19200", "38400",
              "57600", "115200", "230400", "460800", "921600"]
MAX_EVENTS = 6000
MAX_HISTORY = 200

BASE_WINDOW_TITLE = f"{__app_name__} v{__version__} - Serial Monitor"


def window_title(project_path: str | None) -> str:
    """Window title for the given active project file, or none."""
    if not project_path:
        return BASE_WINDOW_TITLE
    return f"{__app_name__} v{__version__} — {Path(project_path).name}"

# Column layout of the Sequence Group table.
GROUP_COL_ON = 0
GROUP_COL_NAME = 1
GROUP_COL_STEPS = 2
GROUP_COL_SEND = 3
GROUP_COL_STATUS = 4


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = config.load()
        self._config_snapshot = deepcopy(self.cfg)
        self.worker: SerialWorker | None = None
        self.rx_monitor = RxMonitor()
        self.runner: SequenceRunner | None = None
        self.group_runner: SequenceGroupRunner | None = None
        self.shortcuts: list[dict] = list(self.cfg.get("shortcuts", []))
        self.steps: list[Step] = [Step.from_dict(d) for d in self.cfg.get("sequence", [])]
        self.sequence_groups: list[NamedSequence] = [
            NamedSequence.from_dict(d) for d in self.cfg.get("sequence_groups", [])
        ]
        self.history: list[dict] = list(self.cfg.get("history", []))
        self.events: deque = deque(maxlen=MAX_EVENTS)
        self._filter_regex = None
        self._building_table = False
        self._building_group_table = False
        self._history_nav_index = -1  # -1 = not navigating
        self._history_nav_pending = ""  # text before navigation started
        self._history_nav_setting = False  # guard for programmatic text changes
        self.mode = "dark"
        self.colors = theme.COLORS["dark"]
        self._monitor_font_pt = clamp_font_point_size(
            self.cfg.get("monitor_font_point_size", DEFAULT_FONT_POINT_SIZE))
        # RX line-assembly (line mode)
        self._rx_buf = bytearray()
        self._rx_line_start = True
        self._panel_parser = PanelProtocolParser()
        self._rx_flush_timer = QTimer(self)
        self._rx_flush_timer.setSingleShot(True)
        self._rx_flush_timer.timeout.connect(self._flush_rx_buffer)

        # Path of the .msproj currently open, set only by opening or saving one.
        # Deliberately not derived from the saved config, which may be stale.
        self._project_path: str | None = None
        self.setWindowTitle(window_title(None))
        self.resize(1280, 780)
        self._build_ui()
        self._load_settings_into_ui()
        self.refresh_ports()
        self._rebuild_sequence_table()
        self._rebuild_group_table()
        self._rebuild_shortcuts()
        self._rebuild_history()

    # --------------------------------------------------------- history nav
    def eventFilter(self, obj, event):
        if obj is self.send_input and event.type() == event.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Up:
                self._nav_history(1)
                return True
            if key == Qt.Key.Key_Down:
                self._nav_history(-1)
                return True
        return super().eventFilter(obj, event)

    def _nav_history(self, direction: int) -> None:
        if not self.history:
            return
        if self._history_nav_index == -1:
            self._history_nav_pending = self.send_input.text()
            self._history_nav_index = 0
        else:
            self._history_nav_index += direction
        if self._history_nav_index < 0:
            self._history_nav_index = -1
            self._history_nav_setting = True
            self.send_input.setText(self._history_nav_pending)
            self._history_nav_setting = False
            return
        if self._history_nav_index >= len(self.history):
            self._history_nav_index = -1
            self._history_nav_setting = True
            self.send_input.setText(self._history_nav_pending)
            self._history_nav_setting = False
            return
        entry = self.history[self._history_nav_index]
        self._history_nav_setting = True
        self.send_input.setText(entry.get("text", ""))
        self._history_nav_setting = False
        self.send_fmt_combo.setCurrentText(utils.normalize_format(entry.get("fmt", "ASCII")))
        self.line_ending_combo.setCurrentText(entry.get("line_ending", "CRLF (\\r\\n)"))
        self.custom_suffix_edit.setText(entry.get("custom_suffix", ""))

    def _on_send_input_changed(self, _text: str) -> None:
        if not self._history_nav_setting:
            self._history_nav_index = -1
            self._history_nav_pending = ""

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        root.addLayout(self._build_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_connection_panel())
        splitter.addWidget(self._build_center_panel())
        splitter.addWidget(self._build_side_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([280, 620, 360])
        root.addWidget(splitter, 1)

        self.status = self.statusBar()
        self.status.showMessage("Disconnected")

    def _build_header(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(8)
        logo = QLabel()
        logo.setPixmap(app_logo_pixmap(36))
        logo.setFixedSize(36, 36)
        logo.setScaledContents(True)
        logo.setToolTip(__app_name__)
        bar.addWidget(logo)
        title = QLabel(f"{__app_name__}")
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        title.setFont(f)
        self.about_btn = QPushButton("About")
        self.about_btn.setToolTip("About MegaSerial")
        self.about_btn.clicked.connect(self.show_about)
        self.donation_btn = QPushButton("Donation")
        self.donation_btn.setToolTip("Support MegaSerial development")
        self.donation_btn.clicked.connect(self.show_donation)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_row.addWidget(title)
        title_row.addWidget(self.about_btn)
        title_row.addWidget(self.donation_btn)
        title_box = QWidget()
        title_box.setLayout(title_row)
        bar.addWidget(title_box)
        subtitle = QLabel("serial monitor for embedded work")
        subtitle.setStyleSheet("color: palette(mid);")
        bar.addWidget(subtitle)
        bar.addStretch(1)
        bar.addWidget(QLabel("Project"))
        self.project_name_edit = QLineEdit()
        self.project_name_edit.setPlaceholderText("Project name")
        self.project_name_edit.setMinimumWidth(140)
        bar.addWidget(self.project_name_edit)
        self.save_project_btn = QPushButton("Save")
        self.save_project_btn.setToolTip("Save project (sequences, settings, log)")
        self.save_project_btn.clicked.connect(self.save_project)
        self.import_project_btn = QPushButton("Import")
        self.import_project_btn.setToolTip("Import a saved project file")
        self.import_project_btn.clicked.connect(self.import_project)
        bar.addWidget(self.save_project_btn)
        bar.addWidget(self.import_project_btn)
        bar.addSpacing(12)
        bar.addWidget(QLabel("Theme"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["System", "Dark", "Light"])
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        bar.addWidget(self.theme_combo)
        return bar

    def show_about(self) -> None:
        AboutDialog(self).exec()

    def show_donation(self) -> None:
        DonationDialog(self).exec()

    def _build_connection_panel(self) -> QWidget:
        box = QGroupBox("Connection")
        outer = QVBoxLayout(box)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        port_row = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.refresh_btn = QPushButton("⟳")
        self.refresh_btn.setFixedWidth(42)
        self.refresh_btn.setToolTip("Refresh port list")
        self.refresh_btn.clicked.connect(self.refresh_ports)
        port_row.addWidget(self.port_combo, 1)
        port_row.addWidget(self.refresh_btn)
        form.addRow("Port", port_row)

        self.baud_combo = QComboBox()
        self.baud_combo.setEditable(True)
        self.baud_combo.addItems(BAUD_RATES)
        form.addRow("Baud", self.baud_combo)

        self.databits_combo = QComboBox()
        self.databits_combo.addItems(["5", "6", "7", "8"])
        self.databits_combo.setCurrentText("8")
        form.addRow("Data bits", self.databits_combo)

        self.parity_combo = QComboBox()
        self.parity_combo.addItems(["None", "Even", "Odd", "Mark", "Space"])
        form.addRow("Parity", self.parity_combo)

        self.stopbits_combo = QComboBox()
        self.stopbits_combo.addItems(["1", "1.5", "2"])
        form.addRow("Stop bits", self.stopbits_combo)

        self.rtscts_check = QCheckBox("RTS/CTS")
        self.xonxoff_check = QCheckBox("XON/XOFF")
        flow_row = QHBoxLayout()
        flow_row.addWidget(self.rtscts_check)
        flow_row.addWidget(self.xonxoff_check)
        form.addRow("Flow", flow_row)
        outer.addLayout(form)

        sig_row = QHBoxLayout()
        self.dtr_btn = QPushButton("DTR")
        self.dtr_btn.setCheckable(True)
        self.dtr_btn.toggled.connect(lambda v: self.worker and self.worker.set_dtr(v))
        self.rts_btn = QPushButton("RTS")
        self.rts_btn.setCheckable(True)
        self.rts_btn.toggled.connect(lambda v: self.worker and self.worker.set_rts(v))
        sig_row.addWidget(self.dtr_btn)
        sig_row.addWidget(self.rts_btn)
        outer.addLayout(sig_row)

        self.autoreconnect_check = QCheckBox("Auto-reconnect if the device drops")
        self.autoreconnect_check.setChecked(True)
        self.autoreconnect_check.toggled.connect(self._on_autoreconnect_changed)
        outer.addWidget(self.autoreconnect_check)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setObjectName("accent")
        self.connect_btn.clicked.connect(self.toggle_connection)
        outer.addWidget(self.connect_btn)

        self.conn_status = QLabel("● Disconnected")
        self.conn_status.setStyleSheet("color: palette(mid);")
        outer.addWidget(self.conn_status)
        outer.addStretch(1)

        box.setMinimumWidth(250)
        return box

    def _build_center_panel(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)

        # monitor toolbar (global options)
        tb = QHBoxLayout()
        self.ts_check = QCheckBox("Timestamps")
        self.delay_check = QCheckBox("Delays")
        self.delay_check.setToolTip("Show time elapsed since the previous monitor entry")
        self.dir_check = QCheckBox("Direction")
        self.autoscroll_check = QCheckBox("Autoscroll")
        self.linemode_check = QCheckBox("Line mode")
        self.linemode_check.setToolTip(
            "Assemble incoming bytes into one entry per line (best for text/AT data)")
        self.linenum_check = QCheckBox("Line numbers")
        self.linenum_check.setToolTip("Show line numbers in the log view")
        self.linenum_check.toggled.connect(self._rerender_all)
        self.split_check = QCheckBox("Split view")
        for chk in (self.ts_check, self.delay_check, self.dir_check, self.autoscroll_check, self.linenum_check):
            chk.toggled.connect(self._rerender_all)
            tb.addWidget(chk)
        self.linemode_check.toggled.connect(self._on_linemode_toggled)
        tb.addWidget(self.linemode_check)
        self.split_check.toggled.connect(self._on_split_toggled)
        tb.addWidget(self.split_check)
        self.graph_view_check = QCheckBox("Graph view")
        self.graph_view_check.setToolTip(
            "Split the monitor vertically: data on top, live graph below")
        self.graph_view_check.toggled.connect(self._on_graph_view_toggled)
        tb.addWidget(self.graph_view_check)
        tb.addStretch(1)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_monitor)
        self.save_btn = QPushButton("Save log")
        self.save_btn.clicked.connect(self.save_log)
        self.save_csv_btn = QPushButton("Export CSV")
        self.save_csv_btn.setToolTip("Export the shown log entries as structured CSV")
        self.save_csv_btn.clicked.connect(self.export_log_csv)
        tb.addWidget(self.clear_btn)
        tb.addWidget(self.save_btn)
        tb.addWidget(self.save_csv_btn)
        v.addLayout(tb)

        mode_row = QHBoxLayout()
        self.presentation_combo = QComboBox()
        self.presentation_combo.addItems(["Normal Monitor View", "Panel View"])
        self.presentation_combo.currentIndexChanged.connect(self._on_presentation_changed)
        mode_row.addWidget(self.presentation_combo)
        self.panel_config_btn = QPushButton("Configure panels…")
        mode_row.addWidget(self.panel_config_btn)
        mode_row.addStretch(1)
        v.addLayout(mode_row)

        # regex filter row
        fb = QHBoxLayout()
        self.filter_check = QCheckBox("Filter")
        self.filter_check.setToolTip("Show only lines matching the regex pattern")
        self.filter_pattern = QLineEdit()
        self.filter_pattern.setPlaceholderText("Regex pattern, e.g. temp|ERROR|^OK")
        self.filter_dir_combo = QComboBox()
        self.filter_dir_combo.addItem("All", "all")
        self.filter_dir_combo.addItem("RX only", "rx")
        self.filter_dir_combo.addItem("TX only", "tx")
        self.filter_ci_check = QCheckBox("Ignore case")
        self.filter_status = QLabel("")
        self.filter_status.setStyleSheet("color: palette(mid);")
        for w in (self.filter_check, self.filter_ci_check):
            w.toggled.connect(self._on_filter_changed)
        self.filter_pattern.textChanged.connect(self._on_filter_changed)
        self.filter_dir_combo.currentIndexChanged.connect(self._on_filter_changed)
        fb.addWidget(self.filter_check)
        fb.addWidget(self.filter_pattern, 1)
        self.panel_view = PanelView(self._monitor_font_pt, self.zoom_monitor)
        self.panel_view.changed.connect(self._rerender_all)
        self.panel_config_btn.clicked.connect(self.panel_view.configure)
        fb.addWidget(self.panel_view.scope_button)
        self.panel_view.scope_button.hide()
        fb.addWidget(self.filter_dir_combo)
        fb.addWidget(self.filter_ci_check)
        fb.addWidget(self.filter_status)
        v.addLayout(fb)

        # monitor (top) + optional graph (bottom)
        self.center_splitter = QSplitter(Qt.Orientation.Vertical)
        self.view_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.view1 = MonitorView(fmt=self.cfg.get("view1_format", "ASCII"),
                                 bytes_per_row=self.cfg.get("view1_bytes_per_row", 16),
                                 on_settings_changed=self._rerender_view,
                                 font_point_size=self._monitor_font_pt,
                                 on_zoom_requested=self.zoom_monitor)
        self.view2 = MonitorView(fmt=self.cfg.get("view2_format", "HEX"),
                                 bytes_per_row=self.cfg.get("view2_bytes_per_row", 16),
                                 on_settings_changed=self._rerender_view,
                                 font_point_size=self._monitor_font_pt,
                                 on_zoom_requested=self.zoom_monitor)
        self.view_splitter.addWidget(self.view1)
        self.view_splitter.addWidget(self.view2)
        self.views = [self.view1, self.view2]
        self._install_zoom_shortcuts()
        self.graph_panel = GraphPanel()
        self.graph_panel.mode_combo.currentIndexChanged.connect(self._on_graph_settings_changed)
        self.presentation_stack = QStackedWidget()
        self.presentation_stack.addWidget(self.view_splitter)
        self.presentation_stack.addWidget(self.panel_view)
        self.center_splitter.addWidget(self.presentation_stack)
        self.center_splitter.addWidget(self.graph_panel)
        self.center_splitter.setStretchFactor(0, 3)
        self.center_splitter.setStretchFactor(1, 2)
        self.graph_panel.setVisible(False)
        v.addWidget(self.center_splitter, 1)

        # send bar
        send_box = QGroupBox("Send")
        sv = QVBoxLayout(send_box)
        row = QHBoxLayout()
        self.clear_after_send_check = QCheckBox("Clear after send")
        self.clear_after_send_check.setToolTip("Clear the input field after sending data")
        row.addWidget(self.clear_after_send_check)
        self.send_input = QLineEdit()
        self.send_input.setPlaceholderText("Type data and press Enter to send…")
        self.send_input.returnPressed.connect(self.send_current)
        self.send_input.installEventFilter(self)
        self.send_input.textChanged.connect(self._on_send_input_changed)
        row.addWidget(self.send_input, 1)
        self.send_fmt_combo = QComboBox()
        self.send_fmt_combo.addItems(utils.FORMATS)
        row.addWidget(self.send_fmt_combo)
        self.line_ending_combo = QComboBox()
        self.line_ending_combo.addItems(utils.LINE_ENDING_LABELS)
        self.line_ending_combo.currentTextChanged.connect(self._sync_custom_suffix)
        row.addWidget(self.line_ending_combo)
        # Only shown for the "Custom" line ending, so the send bar stays compact.
        self.custom_suffix_edit = QLineEdit()
        self.custom_suffix_edit.setPlaceholderText("Suffix, e.g. \\r\\n or \\x00")
        self.custom_suffix_edit.setToolTip(
            "Bytes appended after the payload. Supports \\r \\n \\t \\0 and \\xNN escapes.")
        self.custom_suffix_edit.setMaximumWidth(160)
        self.custom_suffix_edit.setVisible(False)
        row.addWidget(self.custom_suffix_edit)
        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("accent")
        self.send_btn.clicked.connect(self.send_current)
        row.addWidget(self.send_btn)
        self.save_shortcut_btn = QPushButton("★ Save")
        self.save_shortcut_btn.setToolTip("Save this command as a shortcut")
        self.save_shortcut_btn.clicked.connect(self.save_current_as_shortcut)
        row.addWidget(self.save_shortcut_btn)
        sv.addLayout(row)
        v.addWidget(send_box)
        return wrap

    def _build_side_panel(self) -> QWidget:
        tabs = QTabWidget()
        tabs.addTab(self._build_shortcuts_tab(), "Shortcuts")
        tabs.addTab(self._build_history_tab(), "History")
        tabs.addTab(self._build_sequence_tab(), "Sequence")
        tabs.addTab(self._build_sequence_group_tab(), "Sequence Group")
        tabs.setMinimumWidth(340)
        return tabs

    def _build_history_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        hint = QLabel("Commands you sent manually. Double-click to load into the send bar.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        v.addWidget(hint)
        self.history_list = QListWidget()
        self.history_list.itemDoubleClicked.connect(lambda _: self.use_history())
        v.addWidget(self.history_list, 1)
        row = QHBoxLayout()
        for label, slot in [("Resend", self.resend_history), ("Use", self.use_history),
                            ("★ Save", self.save_history_as_shortcut), ("Clear", self.clear_history)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            if label == "Resend":
                b.setObjectName("accent")
            row.addWidget(b)
        v.addLayout(row)
        return w

    def _build_shortcuts_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        hint = QLabel("Saved commands. Double-click to send.")
        hint.setStyleSheet("color: palette(mid);")
        v.addWidget(hint)
        self.shortcut_list = QListWidget()
        self.shortcut_list.itemDoubleClicked.connect(lambda _: self.send_shortcut())
        v.addWidget(self.shortcut_list, 1)
        row = QHBoxLayout()
        for label, slot in [("Send", self.send_shortcut), ("Add", self.add_shortcut),
                            ("Edit", self.edit_shortcut), ("Remove", self.remove_shortcut)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            if label == "Send":
                b.setObjectName("accent")
            row.addWidget(b)
        v.addLayout(row)
        return w

    def _build_sequence_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        hint = QLabel("Steps run top to bottom. Double-click to edit.")
        hint.setStyleSheet("color: palette(mid);")
        v.addWidget(hint)

        self.seq_table = QTableWidget(0, 6)
        self.seq_table.setHorizontalHeaderLabels(["On", "Name", "Advance", "Delay/TO", "Expect", "Status"])
        self.seq_table.verticalHeader().setVisible(False)
        self.seq_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.seq_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.seq_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.seq_table.doubleClicked.connect(lambda _: self.edit_step())
        self.seq_table.itemChanged.connect(self._on_seq_item_changed)
        hh = self.seq_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in (2, 3, 4, 5):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        v.addWidget(self.seq_table, 1)

        btn_row = QGridLayout()
        buttons = [
            ("Add", self.add_step), ("Edit", self.edit_step),
            ("Duplicate", self.duplicate_step), ("Remove", self.remove_step),
            ("↑ Up", self.move_step_up), ("↓ Down", self.move_step_down),
        ]
        for i, (label, slot) in enumerate(buttons):
            b = QPushButton(label)
            b.clicked.connect(slot)
            btn_row.addWidget(b, i // 3, i % 3)
        v.addLayout(btn_row)

        io_row = QHBoxLayout()
        self.import_btn = QPushButton("Import CSV")
        self.import_btn.clicked.connect(self.import_sequence_csv)
        self.export_btn = QPushButton("Export CSV")
        self.export_btn.clicked.connect(self.export_sequence_csv)
        io_row.addWidget(self.import_btn)
        io_row.addWidget(self.export_btn)
        v.addLayout(io_row)

        self.loop_controls = SequenceLoopControls()
        v.addWidget(self.loop_controls)

        self.seq_progress = QProgressBar()
        self.seq_progress.setTextVisible(True)
        v.addWidget(self.seq_progress)

        run_row = QHBoxLayout()
        self.run_btn = QPushButton("▶ Run sequence")
        self.run_btn.setObjectName("accent")
        self.run_btn.clicked.connect(self.run_sequence)
        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_sequence)
        run_row.addWidget(self.run_btn, 1)
        run_row.addWidget(self.stop_btn)
        v.addLayout(run_row)
        return w

    def _build_sequence_group_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        hint = QLabel(
            "Run multiple named sequences in order. Select a row to edit, "
            "or use Send on a row to run one sequence.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        v.addWidget(hint)

        self.group_table = QTableWidget(0, 5)
        self.group_table.setHorizontalHeaderLabels(["On", "Name", "Steps", "Send", "Status"])
        self.group_table.verticalHeader().setVisible(False)
        self.group_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.group_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.group_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.group_table.doubleClicked.connect(lambda _: self.edit_group_sequence())
        self.group_table.itemChanged.connect(self._on_group_item_changed)
        gh = self.group_table.horizontalHeader()
        gh.setSectionResizeMode(GROUP_COL_NAME, QHeaderView.ResizeMode.Stretch)
        for c in (GROUP_COL_ON, GROUP_COL_STEPS, GROUP_COL_SEND, GROUP_COL_STATUS):
            gh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        v.addWidget(self.group_table, 1)

        btn_row = QGridLayout()
        buttons = [
            ("New", self.new_group_sequence), ("Edit", self.edit_group_sequence),
            ("Duplicate", self.duplicate_group_sequence), ("Remove", self.remove_group_sequence),
            ("↑ Up", self.move_group_sequence_up), ("↓ Down", self.move_group_sequence_down),
        ]
        for i, (label, slot) in enumerate(buttons):
            b = QPushButton(label)
            b.clicked.connect(slot)
            btn_row.addWidget(b, i // 3, i % 3)
        v.addLayout(btn_row)

        ctrl_row = QHBoxLayout()
        self.group_delay = QSpinBox()
        self.group_delay.setRange(0, 3_600_000)
        self.group_delay.setSuffix(" ms")
        ctrl_row.addWidget(QLabel("Delay between"))
        ctrl_row.addWidget(self.group_delay)
        self.group_loop_check = QCheckBox("Loop")
        ctrl_row.addWidget(self.group_loop_check)
        ctrl_row.addStretch(1)
        v.addLayout(ctrl_row)

        self.group_progress = QProgressBar()
        self.group_progress.setTextVisible(True)
        v.addWidget(self.group_progress)

        run_row = QHBoxLayout()
        self.group_run_btn = QPushButton("▶ Run all")
        self.group_run_btn.setObjectName("accent")
        self.group_run_btn.clicked.connect(self.run_sequence_group)
        self.group_stop_btn = QPushButton("■ Stop")
        self.group_stop_btn.setObjectName("danger")
        self.group_stop_btn.setEnabled(False)
        self.group_stop_btn.clicked.connect(self.stop_sequence)
        run_row.addWidget(self.group_run_btn, 1)
        run_row.addWidget(self.group_stop_btn)
        v.addLayout(run_row)
        return w

    # ------------------------------------------------------ settings <-> UI
    def _load_settings_into_ui(self) -> None:
        c = self.cfg
        self._monitor_font_pt = clamp_font_point_size(
            c.get("monitor_font_point_size", DEFAULT_FONT_POINT_SIZE))
        self.theme_combo.setCurrentText(c.get("theme", "system").capitalize())
        self._apply_theme(c.get("theme", "system"))
        self.baud_combo.setCurrentText(str(c.get("baudrate", 115200)))
        self.databits_combo.setCurrentText(str(c.get("bytesize", 8)))
        parity_rev = {"N": "None", "E": "Even", "O": "Odd", "M": "Mark", "S": "Space"}
        self.parity_combo.setCurrentText(parity_rev.get(c.get("parity", "N"), "None"))
        self.stopbits_combo.setCurrentText(str(c.get("stopbits", 1)))
        self.rtscts_check.setChecked(c.get("rtscts", False))
        self.xonxoff_check.setChecked(c.get("xonxoff", False))
        self.autoreconnect_check.setChecked(c.get("auto_reconnect", True))
        self.ts_check.setChecked(c.get("show_timestamps", True))
        self.delay_check.setChecked(c.get("show_delays", False))
        self.dir_check.setChecked(c.get("show_direction", True))
        self.autoscroll_check.setChecked(c.get("autoscroll", True))
        self.linenum_check.setChecked(c.get("show_line_numbers", False))
        self.linemode_check.setChecked(c.get("line_mode", True))
        self.send_fmt_combo.setCurrentText(c.get("send_format", "ASCII"))
        self.line_ending_combo.setCurrentText(c.get("line_ending", "CRLF (\\r\\n)"))
        self.custom_suffix_edit.setText(c.get("line_ending_custom_suffix", ""))
        self._sync_custom_suffix()
        self.loop_controls.set_loop(loop_from_settings(c))
        self.group_delay.setValue(c.get("group_delay_ms", 0))
        self.group_loop_check.setChecked(c.get("group_loop", False))
        self.project_name_edit.setText(c.get("project_name", ""))
        self.clear_after_send_check.setChecked(c.get("clear_after_send", False))
        self.split_check.setChecked(c.get("split_view", False))
        self._on_split_toggled(self.split_check.isChecked())
        self.filter_check.setChecked(c.get("filter_enabled", False))
        self.filter_pattern.setText(c.get("filter_pattern", ""))
        dir_idx = self.filter_dir_combo.findData(c.get("filter_direction", "all"))
        if dir_idx >= 0:
            self.filter_dir_combo.setCurrentIndex(dir_idx)
        self.filter_ci_check.setChecked(c.get("filter_case_insensitive", False))
        self._compile_filter()
        self.graph_view_check.setChecked(c.get("graph_view", False))
        self.graph_panel.load_settings(c)
        self._on_graph_view_toggled(self.graph_view_check.isChecked())

    def _collect_settings(self) -> dict:
        parity_map = {"None": "N", "Even": "E", "Odd": "O", "Mark": "M", "Space": "S"}
        self.cfg.update({
            "theme": self.theme_combo.currentText().lower(),
            "show_timestamps": self.ts_check.isChecked(),
            "show_delays": self.delay_check.isChecked(),
            "show_direction": self.dir_check.isChecked(),
            "autoscroll": self.autoscroll_check.isChecked(),
            "show_line_numbers": self.linenum_check.isChecked(),
            "monitor_font_point_size": self._monitor_font_pt,
            "line_mode": self.linemode_check.isChecked(),
            "send_format": self.send_fmt_combo.currentText(),
            "line_ending": self.line_ending_combo.currentText(),
            "line_ending_custom_suffix": self.custom_suffix_edit.text(),
            "last_port": self.port_combo.currentData() or self.port_combo.currentText(),
            "baudrate": int(self.baud_combo.currentText() or 115200),
            "bytesize": int(self.databits_combo.currentText()),
            "parity": parity_map.get(self.parity_combo.currentText(), "N"),
            "stopbits": float(self.stopbits_combo.currentText()),
            "rtscts": self.rtscts_check.isChecked(),
            "xonxoff": self.xonxoff_check.isChecked(),
            "auto_reconnect": self.autoreconnect_check.isChecked(),
            "shortcuts": self.shortcuts,
            "history": self.history,
            "sequence": [s.to_dict() for s in self.steps],
            "sequence_loop_config": self.loop_controls.loop().to_dict(),
            # Kept with their original meaning so older builds reading this file
            # still only loop forever when that is what was selected.
            "sequence_loop": self.loop_controls.loop().mode == LOOP_FOREVER,
            "sequence_loop_delay_ms": self.loop_controls.loop().delay_ms,
            "sequence_groups": [s.to_dict() for s in self.sequence_groups],
            "group_delay_ms": self.group_delay.value(),
            "group_loop": self.group_loop_check.isChecked(),
            "project_name": self.project_name_edit.text().strip(),
            "clear_after_send": self.clear_after_send_check.isChecked(),
            "split_view": self.split_check.isChecked(),
            "view1_format": self.view1.fmt,
            "view1_bytes_per_row": self.view1.bytes_per_row,
            "view2_format": self.view2.fmt,
            "view2_bytes_per_row": self.view2.bytes_per_row,
            "filter_enabled": self.filter_check.isChecked(),
            "filter_pattern": self.filter_pattern.text(),
            "filter_direction": self.filter_dir_combo.currentData(),
            "filter_case_insensitive": self.filter_ci_check.isChecked(),
            "graph_view": self.graph_view_check.isChecked(),
            **self.graph_panel.settings_dict(),
        })
        return self.cfg

    # --------------------------------------------------------------- theme
    def _on_theme_changed(self, _text: str) -> None:
        self._apply_theme(self.theme_combo.currentText().lower())

    def _apply_theme(self, name: str) -> None:
        from PyQt6.QtWidgets import QApplication
        self.mode = theme.apply_theme(QApplication.instance(), name)
        self.colors = theme.COLORS[self.mode]
        if hasattr(self, "graph_panel"):
            self.graph_panel.apply_theme(self.mode)
        if hasattr(self, "views"):
            # The theme stylesheet resets widget fonts, so restore the zoom level.
            self._apply_monitor_zoom()
            self._rerender_all()

    # ----------------------------------------------------------- ports/conn
    def refresh_ports(self) -> None:
        current = self.port_combo.currentData() or self.cfg.get("last_port", "")
        self.port_combo.clear()
        ports = available_ports()
        if not ports:
            self.port_combo.addItem("No ports found", "")
        for dev, desc in ports:
            self.port_combo.addItem(f"{dev}  ({desc})", dev)
        if current:
            idx = self.port_combo.findData(current)
            if idx >= 0:
                self.port_combo.setCurrentIndex(idx)

    def _on_autoreconnect_changed(self, checked: bool) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.set_auto_reconnect(checked)

    def toggle_connection(self) -> None:
        if self.worker and self.worker.is_open:
            self.disconnect_serial()
        else:
            self.connect_serial()

    def connect_serial(self) -> None:
        port = self.port_combo.currentData()
        if not port:
            QMessageBox.warning(self, "No port", "Select a serial port first.")
            return
        parity_map = {"None": "N", "Even": "E", "Odd": "O", "Mark": "M", "Space": "S"}
        try:
            baud = int(self.baud_combo.currentText())
        except ValueError:
            QMessageBox.warning(self, "Invalid baud", "Baud rate must be a number.")
            return
        auto = self.autoreconnect_check.isChecked()
        conf = SerialConfig(
            port=port,
            baudrate=baud,
            bytesize=int(self.databits_combo.currentText()),
            parity=parity_map.get(self.parity_combo.currentText(), "N"),
            stopbits=float(self.stopbits_combo.currentText()),
            rtscts=self.rtscts_check.isChecked(),
            xonxoff=self.xonxoff_check.isChecked(),
            auto_reconnect=auto,
            reconnect_timeout=0.0 if auto else 30.0,
            port_hwid=port_hwid(port),
        )
        self.worker = SerialWorker(conf)
        self.worker.data_received.connect(self.on_data_received)
        self.worker.error.connect(self.on_serial_error)
        self.worker.warning.connect(self.on_serial_warning)
        self.worker.opened.connect(self.on_serial_opened)
        self.worker.closed.connect(self.on_serial_closed)
        self.worker.start()
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("Connecting…")

    def disconnect_serial(self) -> None:
        self.stop_sequence()
        if self.worker:
            self.worker.stop()

    def on_serial_opened(self) -> None:
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Disconnect")
        self._set_connected_ui(True)
        port = self.port_combo.currentData()
        if self.worker and self.worker.port_name != port:
            idx = self.port_combo.findData(self.worker.port_name)
            if idx >= 0:
                self.port_combo.setCurrentIndex(idx)
            port = self.worker.port_name
        port_label = self.port_combo.currentText()
        self.conn_status.setText("● Connected")
        self.conn_status.setStyleSheet(f"color: {theme.ACCENT}; font-weight: 600;")
        self.status.showMessage(f"Connected to {port_label}")
        self._log_line("info", f"Connected to {port_label}")
        # apply current DTR/RTS button states
        self.worker.set_dtr(self.dtr_btn.isChecked())
        self.worker.set_rts(self.rts_btn.isChecked())

    def on_serial_closed(self) -> None:
        self._flush_rx_buffer(force=True)
        self._rx_line_start = True
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Connect")
        self._set_connected_ui(False)
        self.conn_status.setText("● Disconnected")
        self.conn_status.setStyleSheet("color: palette(mid);")
        self.status.showMessage("Disconnected")
        # Join the thread before dropping the reference so the QThread object is
        # never garbage-collected while it is still running.
        if self.worker is not None:
            self.worker.wait(2000)
            self.worker = None

    def on_serial_error(self, message: str) -> None:
        self.connect_btn.setEnabled(True)
        self._log_line("error", message)
        self.status.showMessage(message, 8000)

    def on_serial_warning(self, message: str) -> None:
        # Non-fatal: the read loop keeps running.
        self._log_line("warn", message)
        self.status.showMessage(message, 4000)

    def _set_connected_ui(self, connected: bool) -> None:
        for w in (self.port_combo, self.refresh_btn, self.baud_combo,
                  self.databits_combo, self.parity_combo, self.stopbits_combo,
                  self.rtscts_check, self.xonxoff_check):
            w.setEnabled(not connected)

    # --------------------------------------------------------------- monitor
    def _global_opts(self) -> dict:
        return {
            "show_ts": self.ts_check.isChecked(),
            "show_delays": self.delay_check.isChecked(),
            "show_dir": self.dir_check.isChecked(),
            "show_linenum": self.linenum_check.isChecked(),
            "autoscroll": self.autoscroll_check.isChecked(),
            "colors": self.colors,
        }

    def _on_presentation_changed(self, index):
        self.panel_view.workspace.active = index == 1
        self.presentation_stack.setCurrentIndex(index)
        self.panel_view.scope_button.setVisible(index == 1)
        self.split_check.setEnabled(index == 0)
        self._rerender_all()

    def _panel_filtered_events(self):
        return (ev for ev in self.events
                if self.panel_view.workspace.accepts(panel_event(ev), self._event_passes_filter))

    def _active_views(self) -> list:
        return self.views if self.split_check.isChecked() else [self.view1]

    # ------------------------------------------------------------ monitor zoom
    def _install_zoom_shortcuts(self) -> None:
        for keys, steps in (("Ctrl++", 1), ("Ctrl+=", 1), ("Ctrl+-", -1), ("Ctrl+_", -1)):
            sc = QShortcut(QKeySequence(keys), self)
            sc.activated.connect(lambda s=steps: self.zoom_monitor(s))

    def zoom_monitor(self, steps: int) -> int:
        """Change the shared monitor font size so both views stay in step."""
        self._monitor_font_pt = clamp_font_point_size(self._monitor_font_pt + steps)
        self._apply_monitor_zoom()
        return self._monitor_font_pt

    def _apply_monitor_zoom(self) -> None:
        for view in [*self.views, self.panel_view]:
            view.set_font_point_size(self._monitor_font_pt)

    def _compile_filter(self) -> None:
        pattern = self.filter_pattern.text()
        self._filter_regex = (
            compile_filter(pattern, self.filter_ci_check.isChecked()) if pattern else None
        )
        if self.filter_check.isChecked() and pattern and self._filter_regex is None:
            self.filter_status.setText("Invalid regex")
            self.filter_status.setStyleSheet(
                f"color: {theme.COLORS[self.mode]['error']};")
            self.filter_pattern.setStyleSheet("border: 1px solid #ef4444;")
        else:
            self.filter_status.setText("")
            self.filter_status.setStyleSheet("color: palette(mid);")
            self.filter_pattern.setStyleSheet("")

    def _event_passes_filter(self, ev: dict) -> bool:
        if not self.filter_check.isChecked():
            return True
        if self._filter_regex is None:
            return not self.filter_pattern.text().strip()
        return event_matches_filter(
            ev, self._filter_regex, self.filter_dir_combo.currentData() or "all")

    def _filtered_events(self):
        return (ev for ev in self.events if self._event_passes_filter(ev))

    def _on_filter_changed(self, *_args) -> None:
        self._compile_filter()
        self._rerender_all()

    def _on_graph_view_toggled(self, checked: bool) -> None:
        self.graph_panel.setVisible(checked)
        if checked:
            self._replay_graph()
            total = max(self.center_splitter.height(), 400)
            self.center_splitter.setSizes([int(total * 0.58), int(total * 0.42)])

    def _on_graph_settings_changed(self, *_args) -> None:
        if self.graph_view_check.isChecked():
            self._replay_graph()

    def _replay_graph(self) -> None:
        self.graph_panel.replay_events(self.events)

    def _emit_event(self, ev: dict) -> None:
        visible = list(self._filtered_events())
        prev_ts = visible[-1]["ts"] if visible else None
        evicted = self.events[0] if len(self.events) == self.events.maxlen else None
        self.events.append(ev)
        opts = self._global_opts()
        if self._event_passes_filter(ev):
            for view in self._active_views():
                view.append_event(ev, opts, prev_ts)
        if self.panel_view.workspace.active:
            if evicted is not None:
                self.panel_view.forget_event(evicted)
            self.panel_view.append_event(ev, opts, self._event_passes_filter)
        if self.graph_view_check.isChecked():
            self.graph_panel.feed_event(ev)

    def on_data_received(self, data: bytes) -> None:
        self.rx_monitor.feed(data)   # raw stream for sequence response matching
        if self.linemode_check.isChecked():
            self._ingest_rx_lines(data)
        else:
            self._append_data("rx", data)

    def _ingest_rx_lines(self, data: bytes) -> None:
        """Buffer RX and emit one event per completed line, skipping blank lines."""
        self._rx_buf += data
        while True:
            idx = self._rx_buf.find(b"\n")
            if idx == -1:
                break
            line = bytes(self._rx_buf[:idx + 1])
            del self._rx_buf[:idx + 1]
            if line.strip(b"\r\n"):
                self._append_data("rx", line, complete_line=self._rx_line_start)
            self._rx_line_start = True
        if len(self._rx_buf) > 65536:
            self._flush_rx_buffer(force=True)
        if self._rx_buf:
            self._rx_flush_timer.start(150)
        else:
            self._rx_flush_timer.stop()

    def _flush_rx_buffer(self, force=False) -> None:
        """Emit any buffered partial line (called on timeout or mode change)."""
        if not self._rx_buf:
            return
        line = bytes(self._rx_buf)
        # A potential protocol line may span arbitrarily slow serial reads.
        # Keep it until LF, with a 64 KiB cap; never parse timeout fragments.
        if not force and self._rx_line_start and len(line) <= 65536 and any(
                prefix.startswith(line) or line.startswith(prefix)
                for prefix in (b"@PANEL:", b"@PANEL_TITLE:")):
            return
        self._rx_buf.clear()
        self._rx_line_start = False
        if line.strip(b"\r\n"):
            self._append_data("rx", line)

    def _on_linemode_toggled(self, on: bool) -> None:
        self._flush_rx_buffer(force=True)
        self._rx_line_start = True
        if not on:
            self._rx_flush_timer.stop()

    def _append_data(self, direction: str, data: bytes, *, complete_line=False) -> None:
        ev = {"type": "data", "dir": direction, "ts": datetime.now(), "data": data}
        if direction == "rx" and complete_line:
            command = self._panel_parser.parse(data)
            if command.kind != "normal":
                ev["panel_id"] = command.panel_id
                if command.kind == "data":
                    ev["panel_payload"] = command.text
                else:
                    ev["panel_title"] = command.text
                    if self.panel_view.workspace.update_title(command.panel_id, command.text):
                        self.panel_view.refresh_titles()
        self._emit_event(ev)

    def _log_line(self, kind: str, message: str) -> None:
        self._emit_event({"type": "log", "kind": kind, "ts": datetime.now(), "msg": message})

    def _rerender_view(self, view) -> None:
        view.rerender(self._filtered_events(), self._global_opts())

    def _rerender_all(self, *_args) -> None:
        opts = self._global_opts()
        for view in self._active_views():
            view.rerender(self._filtered_events(), opts)
        if self.panel_view.workspace.active:
            self.panel_view.rerender(self.events, opts, self._event_passes_filter)

    def _on_split_toggled(self, checked: bool) -> None:
        self.view2.setVisible(checked)
        if checked:
            self.view2.rerender(self._filtered_events(), self._global_opts())
            if self.view_splitter.sizes()[1] == 0:
                total = max(self.view_splitter.width(), 400)
                self.view_splitter.setSizes([total // 2, total // 2])

    def clear_monitor(self) -> None:
        self.events.clear()
        self._rx_buf.clear()
        self._rx_line_start = True
        self._rx_flush_timer.stop()
        self.panel_view.clear()
        for view in self.views:
            view.clear()
        self.graph_panel.clear()

    def save_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save log", "serial-log.txt",
                                              "Text files (*.txt);;All files (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.panel_view.plain_text() if self.panel_view.workspace.active
                         else self.view1.plain_text())
            self.status.showMessage(f"Log saved to {path}", 5000)
        except OSError as exc:
            QMessageBox.warning(self, "Save failed", str(exc))

    def export_log_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export log CSV", "serial-log.csv",
                                              "CSV files (*.csv);;All files (*)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            if self.panel_view.workspace.active:
                count = write_events_csv(path, self._panel_filtered_events(),
                                         self.panel_view.workspace.titles())
            else:
                count = write_events_csv(path, self._filtered_events())
            self.status.showMessage(f"Exported {count} log entries to {path}", 5000)
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    # ----------------------------------------------------------------- send
    def _write_bytes(self, data: bytes, echo_name: str | None = None) -> bool:
        if not (self.worker and self.worker.is_open):
            self.status.showMessage("Not connected — open a port first.", 4000)
            return False
        ok = self.worker.write(data)
        if ok and self.cfg.get("echo_tx", True):
            self._flush_rx_buffer()   # keep TX/RX ordering sane in line mode
            self._append_data("tx", data)
        return ok

    def _sync_custom_suffix(self, *_args) -> None:
        self.custom_suffix_edit.setVisible(
            self.line_ending_combo.currentText() == utils.LINE_ENDING_CUSTOM)

    def send_current(self) -> None:
        text = self.send_input.text()
        fmt = self.send_fmt_combo.currentText()
        line_ending = self.line_ending_combo.currentText()
        suffix = self.custom_suffix_edit.text()
        try:
            payload = utils.build_payload(text, fmt, line_ending, suffix)
        except utils.ParseError as exc:
            QMessageBox.warning(self, "Invalid data", str(exc))
            return
        if self._write_bytes(payload):
            self._record_history(text, fmt, line_ending, suffix)
            self._history_nav_index = -1
            self._history_nav_pending = ""
            if self.clear_after_send_check.isChecked():
                self.send_input.clear()

    # -------------------------------------------------------------- shortcuts
    def _rebuild_shortcuts(self) -> None:
        self.shortcut_list.clear()
        for sc in self.shortcuts:
            fmt = utils.normalize_format(sc.get("fmt", "ASCII"))
            sc["fmt"] = fmt
            try:
                preview = utils.human_preview(utils.parse_input(sc.get("data", ""), fmt)) if sc.get("data") else ""
            except utils.ParseError:
                preview = "(invalid data)"
            item = QListWidgetItem(f"{sc.get('name', 'Command')}   ·   {fmt}  {preview}")
            self.shortcut_list.addItem(item)

    def send_shortcut(self) -> None:
        row = self.shortcut_list.currentRow()
        if row < 0 or row >= len(self.shortcuts):
            return
        sc = self.shortcuts[row]
        line_ending = sc.get("line_ending", "None")
        suffix = sc.get("custom_suffix", "")
        try:
            payload = utils.build_payload(
                sc.get("data", ""), sc.get("fmt", "ASCII"), line_ending, suffix)
        except utils.ParseError as exc:
            QMessageBox.warning(self, "Invalid shortcut", str(exc))
            return
        if self._write_bytes(payload):
            self._record_history(
                sc.get("data", ""), sc.get("fmt", "ASCII"), line_ending, suffix)

    def add_shortcut(self) -> None:
        dlg = ShortcutDialog(self, {
            "data": self.send_input.text(),
            "fmt": self.send_fmt_combo.currentText(),
            "line_ending": self.line_ending_combo.currentText(),
            "custom_suffix": self.custom_suffix_edit.text(),
        })
        if dlg.exec():
            self.shortcuts.append(dlg.result_dict())
            self._rebuild_shortcuts()

    def save_current_as_shortcut(self) -> None:
        self.add_shortcut()

    def edit_shortcut(self) -> None:
        row = self.shortcut_list.currentRow()
        if row < 0:
            return
        dlg = ShortcutDialog(self, self.shortcuts[row])
        if dlg.exec():
            self.shortcuts[row] = dlg.result_dict()
            self._rebuild_shortcuts()
            self.shortcut_list.setCurrentRow(row)

    def remove_shortcut(self) -> None:
        row = self.shortcut_list.currentRow()
        if row < 0:
            return
        del self.shortcuts[row]
        self._rebuild_shortcuts()

    # ---------------------------------------------------------------- history
    def _record_history(self, text: str, fmt: str, line_ending: str,
                        custom_suffix: str = "") -> None:
        entry = {
            "ts": datetime.now().strftime("%H:%M:%S"),
            "text": text,
            "fmt": fmt,
            "line_ending": line_ending,
            "custom_suffix": custom_suffix,
        }
        self.history.insert(0, entry)
        del self.history[MAX_HISTORY:]
        self._rebuild_history()

    def _rebuild_history(self) -> None:
        self.history_list.clear()
        for h in self.history:
            text = h.get("text", "")
            shown = text if len(text) <= 40 else text[:40] + "…"
            item = QListWidgetItem(f"{h.get('ts', '')}   [{h.get('fmt', 'ASCII')}]  {shown}")
            self.history_list.addItem(item)

    def use_history(self) -> None:
        row = self.history_list.currentRow()
        if row < 0 or row >= len(self.history):
            return
        h = self.history[row]
        self.send_input.setText(h.get("text", ""))
        self.send_fmt_combo.setCurrentText(utils.normalize_format(h.get("fmt", "ASCII")))
        self.line_ending_combo.setCurrentText(h.get("line_ending", "CRLF (\\r\\n)"))
        self.custom_suffix_edit.setText(h.get("custom_suffix", ""))
        self.send_input.setFocus()

    def resend_history(self) -> None:
        row = self.history_list.currentRow()
        if row < 0 or row >= len(self.history):
            return
        h = self.history[row]
        fmt = utils.normalize_format(h.get("fmt", "ASCII"))
        try:
            payload = utils.build_payload(
                h.get("text", ""), fmt, h.get("line_ending", "None"),
                h.get("custom_suffix", ""))
        except utils.ParseError as exc:
            QMessageBox.warning(self, "Invalid data", str(exc))
            return
        self._write_bytes(payload)

    def save_history_as_shortcut(self) -> None:
        row = self.history_list.currentRow()
        if row < 0 or row >= len(self.history):
            return
        h = self.history[row]
        dlg = ShortcutDialog(self, {
            "data": h.get("text", ""),
            "fmt": utils.normalize_format(h.get("fmt", "ASCII")),
            "line_ending": h.get("line_ending", "CRLF (\\r\\n)"),
            "custom_suffix": h.get("custom_suffix", ""),
        })
        if dlg.exec():
            self.shortcuts.append(dlg.result_dict())
            self._rebuild_shortcuts()

    def clear_history(self) -> None:
        self.history.clear()
        self._rebuild_history()

    # --------------------------------------------------------------- sequence
    def _rebuild_sequence_table(self) -> None:
        self._building_table = True
        self.seq_table.setRowCount(len(self.steps))
        for r, step in enumerate(self.steps):
            on = QTableWidgetItem()
            on.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            on.setCheckState(Qt.CheckState.Checked if step.enabled else Qt.CheckState.Unchecked)
            self.seq_table.setItem(r, 0, on)
            self.seq_table.setItem(r, 1, QTableWidgetItem(step.name))
            self.seq_table.setItem(r, 2, QTableWidgetItem(ADVANCE_LABELS.get(step.advance, step.advance)))
            to = f"{step.delay_ms} ms" if step.advance == "time" else f"{step.timeout_ms} ms"
            self.seq_table.setItem(r, 3, QTableWidgetItem(to))
            self.seq_table.setItem(r, 4, QTableWidgetItem(step.expect or "—"))
            self.seq_table.setItem(r, 5, QTableWidgetItem(""))
        self._building_table = False

    def _on_seq_item_changed(self, item: QTableWidgetItem) -> None:
        if self._building_table or item.column() != 0:
            return
        row = item.row()
        if 0 <= row < len(self.steps):
            self.steps[row].enabled = item.checkState() == Qt.CheckState.Checked

    def _current_step_row(self) -> int:
        return self.seq_table.currentRow()

    def add_step(self) -> None:
        dlg = StepDialog(self)
        if dlg.exec():
            self.steps.append(dlg.result_step())
            self._rebuild_sequence_table()

    def edit_step(self) -> None:
        row = self._current_step_row()
        if row < 0 or row >= len(self.steps):
            return
        dlg = StepDialog(self, self.steps[row])
        if dlg.exec():
            self.steps[row] = dlg.result_step()
            self._rebuild_sequence_table()
            self.seq_table.selectRow(row)

    def duplicate_step(self) -> None:
        row = self._current_step_row()
        if row < 0 or row >= len(self.steps):
            return
        self.steps.insert(row + 1, Step.from_dict(self.steps[row].to_dict()))
        self._rebuild_sequence_table()
        self.seq_table.selectRow(row + 1)

    def remove_step(self) -> None:
        row = self._current_step_row()
        if row < 0 or row >= len(self.steps):
            return
        del self.steps[row]
        self._rebuild_sequence_table()

    def move_step_up(self) -> None:
        row = self._current_step_row()
        if row <= 0:
            return
        self.steps[row - 1], self.steps[row] = self.steps[row], self.steps[row - 1]
        self._rebuild_sequence_table()
        self.seq_table.selectRow(row - 1)

    def move_step_down(self) -> None:
        row = self._current_step_row()
        if row < 0 or row >= len(self.steps) - 1:
            return
        self.steps[row + 1], self.steps[row] = self.steps[row], self.steps[row + 1]
        self._rebuild_sequence_table()
        self.seq_table.selectRow(row + 1)

    def run_sequence(self) -> None:
        if not (self.worker and self.worker.is_open):
            QMessageBox.warning(self, "Not connected", "Open a serial port before running a sequence.")
            return
        if not any(s.enabled for s in self.steps):
            QMessageBox.information(self, "Empty sequence", "Add at least one enabled step.")
            return
        loop = self.loop_controls.loop()
        try:
            loop.until_rx_bytes()
        except utils.ParseError as exc:
            QMessageBox.warning(self, "Invalid loop pattern", str(exc))
            return
        self.stop_sequence()
        for r in range(self.seq_table.rowCount()):
            self.seq_table.item(r, 5).setText("")
        self.runner = SequenceRunner(
            self.steps, self.worker.write, self.rx_monitor, loop=loop,
        )
        self.runner.step_started.connect(self._on_step_started)
        self.runner.step_result.connect(self._on_step_result)
        # runner.log emits (message, kind); _log_line takes (kind, message).
        self.runner.log.connect(lambda msg, kind: self._log_line(kind, msg))
        self.runner.progress.connect(self._on_seq_progress)
        self.runner.finished_all.connect(self._on_seq_finished)
        self._set_seq_running(True)
        self.runner.start()

    def stop_sequence(self) -> None:
        if self.runner and self.runner.isRunning():
            self.runner.request_stop()
            self.runner.wait(3000)
        if self.group_runner and self.group_runner.isRunning():
            self.group_runner.request_stop()
            self.group_runner.wait(3000)

    def _set_seq_running(self, running: bool) -> None:
        self.run_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.group_run_btn.setEnabled(not running)
        self.group_stop_btn.setEnabled(running)
        self._set_group_table_enabled(not running)

    def _maybe_beep_on_match(self, steps: list[Step], step_idx: int, status: str) -> None:
        if status == "matched" and 0 <= step_idx < len(steps) and steps[step_idx].beep_on_match:
            sound.play_notification()

    def _on_step_started(self, idx: int, name: str) -> None:
        if 0 <= idx < self.seq_table.rowCount():
            self.seq_table.selectRow(idx)
            self.seq_table.item(idx, 5).setText("running…")

    def _on_step_result(self, idx: int, status: str, detail: str) -> None:
        if not (0 <= idx < self.seq_table.rowCount()):
            return
        item = self.seq_table.item(idx, 5)
        item.setText(status)
        self._maybe_beep_on_match(self.steps, idx, status)

    def import_sequence_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import sequence CSV", "",
                                              "CSV files (*.csv);;All files (*)")
        if not path:
            return
        try:
            steps = steps_from_csv(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Import failed", str(exc))
            return
        if not steps:
            QMessageBox.information(self, "Nothing imported", "No valid steps found in the file.")
            return
        self.steps = steps
        self._rebuild_sequence_table()
        self.status.showMessage(f"Imported {len(steps)} steps from {path}", 5000)

    def export_sequence_csv(self) -> None:
        if not self.steps:
            QMessageBox.information(self, "Empty sequence", "There are no steps to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export sequence CSV", "sequence.csv",
                                              "CSV files (*.csv);;All files (*)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            steps_to_csv(path, self.steps)
            self.status.showMessage(f"Exported {len(self.steps)} steps to {path}", 5000)
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def _on_seq_progress(self, cur: int, total: int) -> None:
        self.seq_progress.setMaximum(total)
        self.seq_progress.setValue(cur)
        self.seq_progress.setFormat(f"Step {cur}/{total}")

    def _on_seq_finished(self, completed: bool) -> None:
        self._set_seq_running(False)
        msg = "Sequence finished" if completed else "Sequence stopped"
        self._log_line("info" if completed else "warn", msg)
        self.status.showMessage(msg, 4000)

    # -------------------------------------------------------- sequence group
    def _rebuild_group_table(self) -> None:
        self._building_group_table = True
        self.group_table.setRowCount(len(self.sequence_groups))
        for r, seq in enumerate(self.sequence_groups):
            enabled = sum(1 for s in seq.steps if s.enabled)
            total = len(seq.steps)
            on = QTableWidgetItem()
            on.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            on.setCheckState(Qt.CheckState.Checked if seq.enabled else Qt.CheckState.Unchecked)
            on.setToolTip("Include this sequence when the whole group runs")
            self.group_table.setItem(r, GROUP_COL_ON, on)
            self.group_table.setItem(r, GROUP_COL_NAME, QTableWidgetItem(seq.name))
            self.group_table.setItem(r, GROUP_COL_STEPS, QTableWidgetItem(f"{enabled}/{total}"))
            send_btn = QPushButton("Send")
            send_btn.clicked.connect(lambda _checked, row=r: self.send_group_sequence(row))
            self.group_table.setCellWidget(r, GROUP_COL_SEND, send_btn)
            self.group_table.setItem(r, GROUP_COL_STATUS, QTableWidgetItem(""))
        self._building_group_table = False

    def _on_group_item_changed(self, item: QTableWidgetItem) -> None:
        if self._building_group_table or item.column() != GROUP_COL_ON:
            return
        row = item.row()
        if 0 <= row < len(self.sequence_groups):
            # Only the group membership changes; the sequence's steps are untouched.
            self.sequence_groups[row].enabled = item.checkState() == Qt.CheckState.Checked

    def _set_group_table_enabled(self, enabled: bool) -> None:
        for r in range(self.group_table.rowCount()):
            w = self.group_table.cellWidget(r, GROUP_COL_SEND)
            if w:
                w.setEnabled(enabled)

    def _current_group_row(self) -> int:
        return self.group_table.currentRow()

    def _clear_group_status(self) -> None:
        for r in range(self.group_table.rowCount()):
            item = self.group_table.item(r, GROUP_COL_STATUS)
            if item:
                item.setText("")

    def new_group_sequence(self) -> None:
        dlg = SequenceEditorDialog(self)
        if dlg.exec():
            self.sequence_groups.append(dlg.result_sequence())
            self._rebuild_group_table()
            self.group_table.selectRow(len(self.sequence_groups) - 1)

    def edit_group_sequence(self) -> None:
        row = self._current_group_row()
        if row < 0 or row >= len(self.sequence_groups):
            return
        dlg = SequenceEditorDialog(self, self.sequence_groups[row])
        if dlg.exec():
            self.sequence_groups[row] = dlg.result_sequence()
            self._rebuild_group_table()
            self.group_table.selectRow(row)

    def duplicate_group_sequence(self) -> None:
        row = self._current_group_row()
        if row < 0 or row >= len(self.sequence_groups):
            return
        orig = self.sequence_groups[row]
        copy = NamedSequence.from_dict(orig.to_dict())
        copy.name = f"{orig.name} (copy)"
        self.sequence_groups.insert(row + 1, copy)
        self._rebuild_group_table()
        self.group_table.selectRow(row + 1)

    def remove_group_sequence(self) -> None:
        row = self._current_group_row()
        if row < 0 or row >= len(self.sequence_groups):
            return
        name = self.sequence_groups[row].name
        if QMessageBox.question(
            self, "Remove sequence",
            f"Remove sequence \"{name}\"?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        del self.sequence_groups[row]
        self._rebuild_group_table()

    def move_group_sequence_up(self) -> None:
        row = self._current_group_row()
        if row <= 0:
            return
        self.sequence_groups[row - 1], self.sequence_groups[row] = (
            self.sequence_groups[row], self.sequence_groups[row - 1])
        self._rebuild_group_table()
        self.group_table.selectRow(row - 1)

    def move_group_sequence_down(self) -> None:
        row = self._current_group_row()
        if row < 0 or row >= len(self.sequence_groups) - 1:
            return
        self.sequence_groups[row + 1], self.sequence_groups[row] = (
            self.sequence_groups[row], self.sequence_groups[row + 1])
        self._rebuild_group_table()
        self.group_table.selectRow(row + 1)

    def send_group_sequence(self, row: int) -> None:
        if not (self.worker and self.worker.is_open):
            QMessageBox.warning(self, "Not connected", "Open a serial port before running a sequence.")
            return
        if row < 0 or row >= len(self.sequence_groups):
            return
        seq = self.sequence_groups[row]
        if not any(s.enabled for s in seq.steps):
            QMessageBox.information(self, "Empty sequence", f"\"{seq.name}\" has no enabled steps.")
            return
        try:
            seq.loop.until_rx_bytes()
        except utils.ParseError as exc:
            QMessageBox.warning(self, "Invalid loop pattern", str(exc))
            return
        self.stop_sequence()
        self._clear_group_status()
        if self.group_table.item(row, GROUP_COL_STATUS):
            self.group_table.item(row, GROUP_COL_STATUS).setText("running…")
        self.group_table.selectRow(row)
        self.runner = SequenceRunner(seq.steps, self.worker.write, self.rx_monitor,
                                     loop=seq.loop)
        self.runner.step_started.connect(
            lambda _idx, _name, r=row: self.group_table.selectRow(r))
        self.runner.step_result.connect(
            lambda step_idx, status, detail, r=row: self._on_single_group_step_result(
                r, step_idx, status, detail))
        self.runner.log.connect(lambda msg, kind: self._log_line(kind, msg))
        self.runner.finished_all.connect(
            lambda ok, r=row: self._on_single_group_finished(r, ok))
        self._set_seq_running(True)
        self.runner.start()

    def _on_single_group_step_result(self, row: int, step_idx: int, status: str, _detail: str) -> None:
        self._set_group_row_status(row, status)
        if 0 <= row < len(self.sequence_groups):
            self._maybe_beep_on_match(self.sequence_groups[row].steps, step_idx, status)

    def _set_group_row_status(self, row: int, status: str) -> None:
        if 0 <= row < self.group_table.rowCount():
            item = self.group_table.item(row, GROUP_COL_STATUS)
            if item:
                item.setText(status)

    def _on_single_group_finished(self, row: int, completed: bool) -> None:
        self._set_group_row_status(row, "done" if completed else "stopped")
        self._set_seq_running(False)
        name = self.sequence_groups[row].name if 0 <= row < len(self.sequence_groups) else "Sequence"
        msg = f"\"{name}\" finished" if completed else f"\"{name}\" stopped"
        self._log_line("info" if completed else "warn", msg)
        self.status.showMessage(msg, 4000)

    def run_sequence_group(self) -> None:
        if not (self.worker and self.worker.is_open):
            QMessageBox.warning(self, "Not connected", "Open a serial port before running sequences.")
            return
        if not self.sequence_groups:
            QMessageBox.information(self, "Empty group", "Add at least one sequence.")
            return
        if not any(any(s.enabled for s in seq.steps)
                   for seq in self.sequence_groups if seq.enabled):
            QMessageBox.information(
                self, "Empty group", "No enabled steps in any enabled sequence.")
            return
        self.stop_sequence()
        self._clear_group_status()
        self.group_runner = SequenceGroupRunner(
            self.sequence_groups, self.worker.write, self.rx_monitor,
            delay_between_ms=self.group_delay.value(),
            loop=self.group_loop_check.isChecked(),
        )
        self.group_runner.sequence_started.connect(self._on_group_seq_started)
        self.group_runner.sequence_finished.connect(self._on_group_seq_finished)
        self.group_runner.step_result.connect(self._on_group_step_result)
        self.group_runner.log.connect(lambda msg, kind: self._log_line(kind, msg))
        self.group_runner.progress.connect(self._on_group_progress)
        self.group_runner.finished_all.connect(self._on_group_finished)
        self._set_seq_running(True)
        self.group_runner.start()

    def _on_group_seq_started(self, idx: int, _name: str) -> None:
        if 0 <= idx < self.group_table.rowCount():
            self.group_table.selectRow(idx)
            if self.group_table.item(idx, GROUP_COL_STATUS):
                self.group_table.item(idx, GROUP_COL_STATUS).setText("running…")

    def _on_group_seq_finished(self, idx: int, _name: str, completed: bool) -> None:
        if 0 <= idx < self.group_table.rowCount():
            self._set_group_row_status(idx, "done" if completed else "stopped")

    def _on_group_step_result(self, seq_idx: int, step_idx: int, status: str, _detail: str) -> None:
        if 0 <= seq_idx < self.group_table.rowCount():
            self._set_group_row_status(seq_idx, status)
        if 0 <= seq_idx < len(self.sequence_groups):
            self._maybe_beep_on_match(self.sequence_groups[seq_idx].steps, step_idx, status)

    def _on_group_progress(self, cur: int, total: int) -> None:
        self.group_progress.setMaximum(total)
        self.group_progress.setValue(cur)
        self.group_progress.setFormat(f"Step {cur}/{total}")

    def _on_group_finished(self, completed: bool) -> None:
        self._set_seq_running(False)
        msg = "Sequence group finished" if completed else "Sequence group stopped"
        self._log_line("info" if completed else "warn", msg)
        self.status.showMessage(msg, 4000)

    # -------------------------------------------------------------- project
    def _set_project_path(self, path: str | None) -> None:
        """Record the active project file and reflect it in the window title."""
        self._project_path = str(path) if path else None
        self.setWindowTitle(window_title(self._project_path))

    def save_project(self) -> None:
        default_name = self._project_path or (
            (self.project_name_edit.text().strip() or "project") + ".msproj")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save project", default_name,
            "MegaSerial project (*.msproj);;JSON files (*.json);;All files (*)")
        if not path:
            return
        if not path.lower().endswith((".msproj", ".json")):
            path += ".msproj"
        data = project_io.collect_project_data(
            project_name=self.project_name_edit.text().strip(),
            settings=self._collect_settings(),
            events=list(self.events),
            panel_view=self.panel_view.workspace.to_dict(),
        )
        try:
            project_io.save_project(path, data)
            self._set_project_path(path)
            self.status.showMessage(f"Project saved to {path}", 5000)
        except OSError as exc:
            QMessageBox.warning(self, "Save failed", str(exc))

    def import_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import project", "",
            "MegaSerial project (*.msproj);;JSON files (*.json);;All files (*)")
        if not path:
            return
        self.open_project(path)

    def open_project(self, path: str) -> bool:
        """Load a project file into the window.

        Shared by File > Open and the command line, so both behave identically.
        Returns True when the project was applied.
        """
        try:
            loaded = project_io.load_project(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "Import failed", str(exc))
            return False

        settings = loaded.get("settings", {})
        if not isinstance(settings, dict):
            QMessageBox.warning(self, "Import failed", "Project settings are invalid.")
            return False

        self._rx_flush_timer.stop()
        self._rx_buf.clear()
        self._rx_line_start = True
        self.panel_view.set_workspace(PanelWorkspace.restore(loaded.get("panel_view")))
        self.presentation_combo.setCurrentIndex(int(self.panel_view.workspace.active))
        self.cfg.update(settings)
        self.shortcuts = list(self.cfg.get("shortcuts", []))
        self.steps = [Step.from_dict(d) for d in self.cfg.get("sequence", [])]
        self.sequence_groups = [
            NamedSequence.from_dict(d) for d in self.cfg.get("sequence_groups", [])
        ]
        self.history = list(self.cfg.get("history", []))
        self.project_name_edit.setText(loaded.get("project_name", "") or self.cfg.get("project_name", ""))

        self._load_settings_into_ui()
        self._rebuild_sequence_table()
        self._rebuild_group_table()
        self._rebuild_shortcuts()
        self._rebuild_history()

        self.events.clear()
        for ev in loaded.get("events", []):
            self.events.append(ev)
        self._rerender_all()
        if self.graph_view_check.isChecked():
            self._replay_graph()

        self._set_project_path(path)
        self.status.showMessage(f"Imported project from {path}", 5000)
        return True

    # ---------------------------------------------------------------- close
    def closeEvent(self, event) -> None:
        self.stop_sequence()
        if self.worker:
            self.worker.stop()
        config.save(self._collect_settings(), snapshot=self._config_snapshot)
        super().closeEvent(event)
