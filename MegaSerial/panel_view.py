"""Panel presentation and configuration, reusing the normal monitor renderer."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QTextCursor, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMenu,
    QDialog, QDialogButtonBox, QSpinBox, QFormLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QScrollArea, QSizePolicy,
)
from .monitor import MonitorView
from .panel_model import PanelWorkspace, MAX_ROWS, MAX_COLUMNS, default_title
from .panel_protocol import panel_event


class PanelLayoutDialog(QDialog):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Panel View")
        self.resize(560, 520)
        self.workspace = workspace
        box = QVBoxLayout(self)
        form = QFormLayout()
        self.rows = QSpinBox()
        self.rows.setRange(1, MAX_ROWS)
        self.rows.setValue(len(workspace.row_counts))
        self.columns = QSpinBox()
        self.columns.setRange(1, MAX_COLUMNS)
        self.columns.setValue(workspace.max_columns)
        form.addRow("Rows", self.rows)
        form.addRow("Maximum columns", self.columns)
        box.addLayout(form)
        self.counts = QTableWidget(0, 1)
        self.counts.setHorizontalHeaderLabels(["Panels in row"])
        box.addWidget(self.counts)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Position", "Panel ID", "Title (optional)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        box.addWidget(self.table, 1)
        box.addWidget(QLabel("IDs are automatic: row 3, column 2 is 32. Titles are optional. General uses cell 11."))
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        box.addWidget(self.buttons)
        self.rows.valueChanged.connect(self._rows_changed)
        self.columns.valueChanged.connect(self._rows_changed)
        self._rows_changed()

    def _rows_changed(self):
        old = [self.counts.cellWidget(i, 0).value() for i in range(self.counts.rowCount())]
        self.counts.setRowCount(self.rows.value())
        for i in range(self.rows.value()):
            spin = QSpinBox()
            spin.setRange(1, self.columns.value())
            spin.setValue(old[i] if i < len(old) else
                          self.workspace.row_counts[i] if i < len(self.workspace.row_counts) else 1)
            self.counts.setCellWidget(i, 0, spin)
            spin.valueChanged.connect(self._panels_changed)
        self._panels_changed()

    def _panels_changed(self):
        old = [{"id": self.table.item(i, 1).text(), "title": self.table.item(i, 2).text()}
               for i in range(self.table.rowCount())]
        titles = {p["id"]: p["title"] for p in (old or self.workspace.panels)}
        counts = [self.counts.cellWidget(i, 0).value() for i in range(self.counts.rowCount())]
        self.table.setRowCount(sum(counts))
        idx = 0
        for row, count in enumerate(counts):
            for col in range(count):
                ident = f"{row + 1}{col + 1}"
                title = titles.get(ident, default_title(ident))
                for column, text in enumerate((f"{row + 1} / {col + 1}", ident, title)):
                    item = QTableWidgetItem(text)
                    if column < 2:
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(idx, column, item)
                idx += 1

    def accept(self):
        state = self.workspace.to_dict()
        state.update(max_columns=self.columns.value(),
                     row_counts=[self.counts.cellWidget(i, 0).value() for i in range(self.counts.rowCount())],
                     panels=[{**next((p for p in self.workspace.panels if p["id"] == self.table.item(i, 1).text()), {}),
                              "id": self.table.item(i, 1).text(), "title": self.table.item(i, 2).text()}
                             for i in range(self.table.rowCount())])
        try:
            self.result_workspace = PanelWorkspace(state)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid layout", str(exc))
            return
        super().accept()


class PanelWidget(QWidget):
    def __init__(self, panel, font_size, on_zoom):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        self.header = QLabel()
        self.header.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.header.setTextFormat(Qt.TextFormat.PlainText)
        self.header.setText(panel["title"])
        self.header.setToolTip("ID: " + panel["id"])
        layout.addWidget(self.header)
        self.monitor = MonitorView(font_point_size=font_size, on_zoom_requested=on_zoom, max_blocks=0)
        # Keep the reusable monitor and hide only its format toolbar.
        head = self.monitor.layout().itemAt(0).layout()
        for i in range(head.count()):
            if head.itemAt(i).widget():
                head.itemAt(i).widget().hide()
        layout.addWidget(self.monitor, 1)


class PanelView(QScrollArea):
    changed = pyqtSignal()

    def __init__(self, font_size, on_zoom):
        super().__init__()
        self.workspace = PanelWorkspace()
        self.font_size, self.on_zoom = font_size, on_zoom
        self.widgets = {}
        self.previous = {}
        self.rendered_blocks = {}
        self.scope_button = QPushButton("Panels ▾")
        self.scope_menu = QMenu(self.scope_button)
        self.scope_button.setMenu(self.scope_menu)
        self.setWidgetResizable(True)
        self.rebuild()

    def configure(self):
        dialog = PanelLayoutDialog(self.workspace, self)
        if dialog.exec():
            self.set_workspace(dialog.result_workspace)

    def set_workspace(self, workspace):
        self.workspace = workspace
        self.rebuild()
        self.changed.emit()

    def rebuild(self):
        old = self.takeWidget()
        if old:
            old.deleteLater()
        body = QWidget()
        layout = QVBoxLayout(body)
        self.widgets = {}
        self.previous = {}
        self.rendered_blocks = {}
        idx = 0
        for count in self.workspace.row_counts:
            row = QHBoxLayout()
            for _ in range(count):
                panel = self.workspace.panels[idx]
                widget = PanelWidget(panel, self.font_size, self.on_zoom)
                self.widgets[panel["id"]] = widget
                row.addWidget(widget, 1)
                idx += 1
            layout.addLayout(row, 1)
        self.setWidget(body)
        self.refresh_titles()

    def refresh_titles(self):
        self.scope_menu.clear()
        all_action = self.scope_menu.addAction("All")
        all_action.setCheckable(True)
        all_action.setChecked(self.workspace.scope is None)
        all_action.triggered.connect(self._all_scope)
        for ident, title in self.workspace.titles().items():
            self.widgets[ident].header.setText(f"{ident} — {title}")
            self.widgets[ident].header.setToolTip(f"{title}\nID: {ident}")
            panel = next(p for p in self.workspace.panels if p["id"] == ident)
            styles = []
            for key, css in (("title_color", "color"), ("title_bg", "background-color")):
                value = panel.get(key, "")
                color = QColor(value if isinstance(value, str) else "")
                if color.isValid():
                    styles.append(f"{css}:{color.name()}")
            self.widgets[ident].header.setStyleSheet(";".join(styles))
            action = self.scope_menu.addAction(f"{title} ({ident})")
            action.setCheckable(True)
            action.setChecked(self.workspace.in_scope(ident))
            action.triggered.connect(lambda checked, ident=ident: self._scope(ident, checked))

    def apply_control(self, ev):
        """Apply a decoded title/style command to its configured destination."""
        panel = next((p for p in self.workspace.panels if p["id"] == ev.get("panel_id")), None)
        if panel is None:
            return
        style = ev.get("panel_style", {})
        if "title" in style:
            self.workspace.update_title(panel["id"], style["title"])
        for key, target in (("color", "title_color"), ("bg", "title_bg")):
            if key not in style:
                continue
            value = style[key].strip()
            color = QColor(value)
            if not color.isValid():
                parts = value.split(',')
                if len(parts) == 3 and all(1 <= len(p.strip()) <= 3 and p.strip().isascii()
                                         and p.strip().isdigit() and 0 <= int(p) <= 255 for p in parts):
                    color = QColor(*(int(p) for p in parts))
            if color.isValid():
                panel[target] = color.name()
            else:
                ev["protocol_diagnostic"] = "Invalid title color"
        self.refresh_titles()

    def _all_scope(self, checked):
        self.workspace.scope = None if checked else []
        self.refresh_titles()
        self.changed.emit()

    def _scope(self, ident, checked):
        if self.workspace.scope is None:
            self.workspace.scope = list(self.widgets)
        selected = set(self.workspace.scope)
        if checked:
            selected.add(ident)
        else:
            selected.discard(ident)
        self.workspace.scope = [i for i in self.widgets if i in selected]
        self.refresh_titles()
        self.changed.emit()

    def set_font_point_size(self, size):
        self.font_size = size
        for widget in self.widgets.values():
            widget.monitor.set_font_point_size(size)

    def append_event(self, ev, opts, predicate):
        if ev.get("panel_control") and ev.get("panel_id") in self.widgets:
            return
        event_key = id(ev)
        ev = panel_event(ev)
        if self.workspace.accepts(ev, predicate):
            ident = self.workspace.destination(ev)
            monitor = self.widgets[ident].monitor
            before = 0 if monitor.edit.document().isEmpty() else monitor.edit.blockCount()
            monitor.append_event(ev, {**opts, "unicode_text": True}, self.previous.get(ident))
            self.rendered_blocks[event_key] = (ident, monitor.edit.blockCount() - before)
            self.previous[ident] = ev.get("ts")

    def forget_event(self, ev):
        """Trim presentation blocks when the shared event deque evicts an entry.

        Only block counts and object identities are cached, never event data.
        """
        entry = self.rendered_blocks.pop(id(ev), None)
        if entry is None:
            return
        ident, count = entry
        edit = self.widgets[ident].monitor.edit
        if count >= edit.blockCount():
            edit.clear()
            self.previous.pop(ident, None)
        else:
            cursor = QTextCursor(edit.document())
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(QTextCursor.MoveOperation.NextBlock,
                                QTextCursor.MoveMode.KeepAnchor, count)
            cursor.removeSelectedText()

    def rerender(self, events, opts, predicate):
        self.clear()
        for ev in events:
            self.append_event(ev, opts, predicate)

    def clear(self):
        self.previous.clear()
        self.rendered_blocks.clear()
        for widget in self.widgets.values():
            widget.monitor.clear()

    def plain_text(self):
        return "\n\n".join(f"{p['title']} ({p['id']})\n{self.widgets[p['id']].monitor.plain_text()}"
                           for p in self.workspace.panels)
