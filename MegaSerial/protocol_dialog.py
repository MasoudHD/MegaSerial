"""Guided protocol profile editor and isolated packet preview."""
from copy import deepcopy
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox, QLineEdit,
    QSpinBox, QCheckBox, QLabel, QPushButton, QPlainTextEdit, QTabWidget,
    QWidget, QTableWidget, QTableWidgetItem, QHeaderView, QDialogButtonBox,
    QFileDialog, QMessageBox,
)
from . import utils
from .protocol_profiles import (preset, validate_profile, ProtocolDecoder, load_profile,
                                save_profile, MAX_PACKET)

PROFILE_LABELS = {"megaserial": "MegaSerial", "zmonitor": "zMonitor",
                  "text": "Custom text line", "frame": "Custom delimited frame"}


class ProtocolDialog(QDialog):
    def __init__(self, profile, panel_titles, latest_rx=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Device protocol")
        self.resize(780, 640)
        self.panel_titles = dict(panel_titles)
        self.latest_rx = latest_rx
        self.original_kind = profile["kind"]
        box = QVBoxLayout(self)
        self.kind = QComboBox()
        for key, label in PROFILE_LABELS.items():
            self.kind.addItem(label, key)
        form = QFormLayout()
        form.addRow("Device protocol", self.kind)
        box.addLayout(form)
        self.layout_check = QCheckBox("Use zMonitor's default 4 × 4 layout (keeps titles at existing positions)")
        box.addWidget(self.layout_check)
        self.description = QLabel()
        self.description.setWordWrap(True)
        box.addWidget(self.description)
        tabs = QTabWidget()
        box.addWidget(tabs, 1)
        packet = QWidget()
        pf = QFormLayout(packet)
        self.prefix = QLineEdit()
        self.separator = QLineEdit()
        self.ending = QComboBox()
        for label, data in (("LF (0A)", "0A"), ("CRLF (0D 0A)", "0D 0A"), ("CR (0D)", "0D")):
            self.ending.addItem(label, data)
        self.ending.setEditable(True)
        self.ending.setToolTip("Choose a line ending or enter 1–8 hexadecimal bytes")
        self.start = QLineEdit()
        self.end = QLineEdit()
        self.encoding = QComboBox()
        self.encoding.addItems(["utf-8", "ascii", "latin-1"])
        self.ansi = QCheckBox("Interpret ANSI text colors")
        for title, widget in (("Text prefix", self.prefix), ("Channel separator", self.separator),
                              ("Line ending", self.ending), ("Frame start (hex)", self.start),
                              ("Frame end (hex)", self.end), ("Text encoding", self.encoding)):
            pf.addRow(title, widget)
        pf.addRow(self.ansi)
        self.advanced_button = QPushButton("Advanced header offsets ▸")
        self.advanced_button.setCheckable(True)
        pf.addRow(self.advanced_button)
        self.advanced = QWidget()
        af = QFormLayout(self.advanced)
        self.channel_offset = QSpinBox()
        self.channel_offset.setRange(0, 63)
        self.payload_offset = QSpinBox()
        self.payload_offset.setRange(1, 64)
        self.channel_bias = QSpinBox()
        self.channel_bias.setRange(0, 255)
        for title, widget in (("Channel byte index after start (0-based)", self.channel_offset),
                              ("Payload byte index after start (0-based)", self.payload_offset),
                              ("Subtract from channel byte (decimal)", self.channel_bias)):
            af.addRow(title, widget)
        pf.addRow(self.advanced)
        self.advanced.hide()
        self.advanced_button.toggled.connect(self.advanced.setVisible)
        tabs.addTab(packet, "Packet format")
        mapping_page = QWidget()
        ml = QVBoxLayout(mapping_page)
        note = QLabel("Map device channels to matrix positions. Unmapped channels go to General.\n"
                      "Custom text channels such as 32 use that position unless overridden here.")
        note.setWordWrap(True)
        ml.addWidget(note)
        self.mapping = QTableWidget(0, 2)
        self.mapping.setHorizontalHeaderLabels(["Device channel", "Destination panel"])
        self.mapping.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        ml.addWidget(self.mapping)
        buttons = QHBoxLayout()
        add = QPushButton("Add channel")
        remove = QPushButton("Remove selected channel")
        add.clicked.connect(lambda: self.add_mapping())
        remove.clicked.connect(lambda: self.mapping.removeRow(self.mapping.currentRow()))
        buttons.addWidget(add)
        buttons.addWidget(remove)
        ml.addLayout(buttons)
        tabs.addTab(mapping_page, "Channel mapping")
        preview = QWidget()
        pv = QVBoxLayout(preview)
        self.sample_format = QComboBox()
        self.sample_format.addItems(["Hex bytes", "Text with escapes (\\n, \\r, \\xNN)"])
        pv.addWidget(self.sample_format)
        self.sample = QPlainTextEdit()
        self.sample.setPlaceholderText("Example zMonitor packet: C8 D2 48 65 6C 6C 6F FA")
        pv.addWidget(self.sample, 1)
        row = QHBoxLayout()
        test = QPushButton("Test packet")
        test.clicked.connect(self.test_packet)
        recent = QPushButton("Use latest RX event")
        recent.setEnabled(latest_rx is not None)
        recent.clicked.connect(self.use_latest)
        row.addWidget(test)
        row.addWidget(recent)
        pv.addLayout(row)
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        pv.addWidget(self.result, 1)
        tabs.addTab(preview, "Test packet")
        bottom = QHBoxLayout()
        imp, exp = QPushButton("Import profile…"), QPushButton("Export profile…")
        imp.clicked.connect(self.import_profile)
        exp.clicked.connect(self.export_profile)
        bottom.addWidget(imp)
        bottom.addWidget(exp)
        bottom.addStretch()
        done = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        done.accepted.connect(self.accept)
        done.rejected.connect(self.reject)
        bottom.addWidget(done)
        box.addLayout(bottom)
        self.kind.currentIndexChanged.connect(self.change_kind)
        self.populate(profile)

    def add_mapping(self, channel="", destination="11"):
        row = self.mapping.rowCount()
        self.mapping.insertRow(row)
        self.mapping.setItem(row, 0, QTableWidgetItem(channel))
        target = QComboBox()
        target.setEditable(True)
        for ident, title in self.panel_titles.items():
            target.addItem(ident)
            target.setItemData(target.count() - 1, title, Qt.ItemDataRole.ToolTipRole)
        if target.findText(destination) < 0:
            target.addItem(destination)
        target.setCurrentText(destination)
        self.mapping.setCellWidget(row, 1, target)

    def change_kind(self):
        self.populate(preset(self.kind.currentData()))
        self.layout_check.setChecked(self.kind.currentData() == "zmonitor" and self.original_kind != "zmonitor")

    def populate(self, profile):
        p = validate_profile(profile)
        self.base = deepcopy(p)
        self.kind.blockSignals(True)
        self.kind.setCurrentIndex(self.kind.findData(p["kind"]))
        self.kind.blockSignals(False)
        for key in ("prefix", "separator", "start", "end"):
            getattr(self, key).setText(p[key])
        idx = self.ending.findData(p["ending"])
        if idx >= 0:
            self.ending.setCurrentIndex(idx)
        else:
            self.ending.setEditText(p["ending"])
        self.encoding.setCurrentText(p["encoding"])
        self.ansi.setChecked(p["ansi"])
        for key in ("channel_offset", "payload_offset", "channel_bias"):
            getattr(self, key).setValue(p[key])
        channel_label = ("Device channel (0–15)" if p["kind"] == "zmonitor" else
                         "Device channel (decimal)" if p["kind"] == "frame" else "Device channel")
        self.mapping.setHorizontalHeaderLabels([channel_label, "Destination panel"])
        self.mapping.setRowCount(0)
        for channel, destination in p["mapping"].items():
            self.add_mapping(channel, destination)
        custom = p["kind"] in ("text", "frame")
        for widget in (self.encoding, self.ansi):
            widget.setEnabled(custom)
        for widget in (self.prefix, self.separator, self.ending):
            widget.setEnabled(p["kind"] == "text")
        for widget in (self.start, self.end, self.advanced_button, self.advanced):
            widget.setEnabled(p["kind"] == "frame")
        self.mapping.setEnabled(p["kind"] != "megaserial")
        self.layout_check.setVisible(p["kind"] == "zmonitor")
        self.description.setText({
            "megaserial": "Existing @PANEL:32|message protocol. Requires Line mode; routing uses position IDs.",
            "zmonitor": "Ready to use: C8 + channel byte + text + FA; channel byte = C9 + channel (0–15). "
                        "Channels map to a 4×4 grid. "
                        "Supports title/style commands and ANSI colors. No newline required.",
            "text": "A complete line contains prefix + channel + separator + payload. "
                    "Uses the ending selected below, independently of Line mode.",
            "frame": "Start bytes + header + text payload + end bytes. Defaults: channel is the first header byte; "
                     "payload follows it. Advanced fields change offsets and channel numbering. "
                     "No escaping, checksums or length-prefixed frames; delimiter bytes cannot occur in the payload.",
        }[p["kind"]])

    def profile(self):
        p = deepcopy(self.base)
        p["kind"] = self.kind.currentData()
        for key in ("prefix", "separator", "start", "end"):
            p[key] = getattr(self, key).text()
        idx = self.ending.currentIndex()
        p["ending"] = (self.ending.itemData(idx) if idx >= 0 and self.ending.currentText() == self.ending.itemText(idx)
                       else self.ending.currentText())
        p["encoding"] = self.encoding.currentText()
        p["ansi"] = self.ansi.isChecked()
        for key in ("channel_offset", "payload_offset", "channel_bias"):
            p[key] = getattr(self, key).value()
        p["mapping"] = {}
        for row in range(self.mapping.rowCount()):
            channel = self.mapping.item(row, 0).text().strip()
            if channel in p["mapping"]:
                raise ValueError(f"Duplicate channel: {channel}")
            p["mapping"][channel] = self.mapping.cellWidget(row, 1).currentText().strip()
        return validate_profile(p)

    def use_latest(self):
        raw = self.latest_rx() if self.latest_rx else b""
        self.sample_format.setCurrentIndex(0)
        self.sample.setPlainText(utils.to_hex(raw[:MAX_PACKET]))

    def test_packet(self):
        try:
            decoder = ProtocolDecoder(self.profile())
            value = self.sample.toPlainText()
            if len(value) > MAX_PACKET * 4:
                raise ValueError("Preview sample is too large (maximum 64 KiB of bytes)")
            raw = utils.parse_hex(value) if self.sample_format.currentIndex() == 0 else utils.parse_ascii(value)
            if len(raw) > MAX_PACKET:
                raise ValueError("Preview sample is too large (maximum 64 KiB)")
            events = decoder.feed(raw)
            lines = []
            configured = set(self.panel_titles)
            if self.layout_check.isChecked() and self.kind.currentData() == 'zmonitor':
                configured = {f'{r}{c}' for r in range(1, 5) for c in range(1, 5)}
            for i, ev in enumerate(events[:20], 1):
                destination = ev.get('panel_id')
                shown = destination if destination in configured else '11 (General fallback)'
                lines.append(f"Packet {i}: {'recognized' if 'device_channel' in ev else 'unrecognized'}\n"
                             f"Channel: {ev.get('device_channel', '—')}\nDestination: {shown}\n"
                             f"Message: {ev.get('panel_payload', ev.get('panel_title', '—'))}\n"
                             f"Control: {ev.get('panel_style', '—')}\n"
                             f"Diagnostic: {ev.get('protocol_diagnostic', 'OK')}")
            if decoder.buffer:
                lines.append(f"Incomplete packet: {len(decoder.buffer)} buffered bytes; waiting for its ending.")
            if len(events) > 20:
                lines.append(f"Showing 20 of {len(events)} packets.")
            self.result.setPlainText('\n\n'.join(lines) or 'No bytes to decode.')
        except ValueError as exc:
            self.result.setPlainText(str(exc))

    def import_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import protocol profile", "", "JSON profiles (*.json)")
        if path:
            try:
                self.populate(load_profile(path))
                self.layout_check.setChecked(False)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Import failed", str(exc))

    def export_profile(self):
        try:
            profile = self.profile()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid profile", str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export protocol profile", "protocol.json", "JSON profiles (*.json)")
        if path:
            try:
                save_profile(path, profile)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Export failed", str(exc))

    def accept(self):
        try:
            self.result_profile = self.profile()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid profile", str(exc))
            return
        super().accept()
