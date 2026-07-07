"""Modal dialogs for editing shortcuts and sequence steps."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QComboBox, QSpinBox,
    QVBoxLayout, QLabel, QPlainTextEdit, QCheckBox, QTableWidget, QTableWidgetItem,
    QGridLayout, QHeaderView, QAbstractItemView, QPushButton,
)

from . import utils
from .sequence import (
    Step, NamedSequence, ADVANCE_MODES, ADVANCE_LABELS, ADVANCE_TIME,
    ON_TIMEOUT_CONTINUE, ON_TIMEOUT_STOP, ON_TIMEOUT_RETRY,
)

_ON_TIMEOUT_LABELS = {
    ON_TIMEOUT_CONTINUE: "Continue to next step",
    ON_TIMEOUT_STOP: "Stop the sequence",
    ON_TIMEOUT_RETRY: "Retry this step",
}


class ShortcutDialog(QDialog):
    """Edit a saved command (shortcut)."""

    def __init__(self, parent=None, shortcut: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Shortcut")
        self.setMinimumWidth(420)
        shortcut = shortcut or {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name = QLineEdit(shortcut.get("name", ""))
        self.name.setPlaceholderText("e.g. Reset device")

        self.data = QLineEdit(shortcut.get("data", ""))
        self.data.setPlaceholderText("Payload to send")

        self.fmt = QComboBox()
        self.fmt.addItems(utils.FORMATS)
        self.fmt.setCurrentText(shortcut.get("fmt", utils.FORMAT_ASCII))

        self.line_ending = QComboBox()
        self.line_ending.addItems(utils.LINE_ENDINGS.keys())
        self.line_ending.setCurrentText(shortcut.get("line_ending", "CRLF (\\r\\n)"))

        form.addRow("Name", self.name)
        form.addRow("Data", self.data)
        form.addRow("Format", self.fmt)
        form.addRow("Line ending", self.line_ending)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_dict(self) -> dict:
        name = self.name.text().strip() or utils.human_preview(
            utils.parse_input(self.data.text(), self.fmt.currentText())
        ) or "Command"
        return {
            "name": name,
            "data": self.data.text(),
            "fmt": self.fmt.currentText(),
            "line_ending": self.line_ending.currentText(),
        }


class StepDialog(QDialog):
    """Edit a single sequence step."""

    def __init__(self, parent=None, step: Step | None = None):
        super().__init__(parent)
        self.setWindowTitle("Sequence step")
        self.setMinimumWidth(480)
        step = step or Step()

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name = QLineEdit(step.name)

        self.data = QPlainTextEdit(step.data)
        self.data.setFixedHeight(60)
        self.data.setPlaceholderText("Payload to send")

        self.fmt = QComboBox()
        self.fmt.addItems(utils.FORMATS)
        self.fmt.setCurrentText(step.fmt)

        self.line_ending = QComboBox()
        self.line_ending.addItems(utils.LINE_ENDINGS.keys())
        self.line_ending.setCurrentText(step.line_ending)

        self.advance = QComboBox()
        for mode in ADVANCE_MODES:
            self.advance.addItem(ADVANCE_LABELS[mode], mode)
        idx = ADVANCE_MODES.index(step.advance) if step.advance in ADVANCE_MODES else 0
        self.advance.setCurrentIndex(idx)
        self.advance.currentIndexChanged.connect(self._sync_enabled)

        self.delay = QSpinBox()
        self.delay.setRange(0, 3_600_000)
        self.delay.setSuffix(" ms")
        self.delay.setValue(step.delay_ms)

        self.expect = QLineEdit(step.expect)
        self.expect.setPlaceholderText("Expected response (leave empty to match any data)")

        self.fail_on = QLineEdit(step.fail_on)
        self.fail_on.setPlaceholderText("Optional: reply that means failure, e.g. ERROR")

        self.expect_fmt = QComboBox()
        self.expect_fmt.addItems(utils.FORMATS)
        self.expect_fmt.setCurrentText(step.expect_fmt)

        self.timeout = QSpinBox()
        self.timeout.setRange(1, 3_600_000)
        self.timeout.setSuffix(" ms")
        self.timeout.setValue(step.timeout_ms)

        self.on_timeout = QComboBox()
        for key, label in _ON_TIMEOUT_LABELS.items():
            self.on_timeout.addItem(label, key)
        self.on_timeout.setCurrentIndex(
            list(_ON_TIMEOUT_LABELS).index(step.on_timeout)
            if step.on_timeout in _ON_TIMEOUT_LABELS else 0)

        self.max_retries = QSpinBox()
        self.max_retries.setRange(0, 100)
        self.max_retries.setValue(step.max_retries)

        self.beep_on_match = QCheckBox("Play a sound when the expected response is received")
        self.beep_on_match.setChecked(step.beep_on_match)

        form.addRow("Name", self.name)
        form.addRow("Data", self.data)
        form.addRow("Format", self.fmt)
        form.addRow("Line ending", self.line_ending)
        form.addRow("Advance when", self.advance)
        form.addRow("Delay", self.delay)
        form.addRow("Expected response", self.expect)
        form.addRow("Fail on (optional)", self.fail_on)
        form.addRow("Response format", self.expect_fmt)
        form.addRow("Response timeout", self.timeout)
        form.addRow("On timeout", self.on_timeout)
        form.addRow("Max retries", self.max_retries)
        form.addRow("On match", self.beep_on_match)
        layout.addLayout(form)

        hint = QLabel(
            "Delay = time-based advance.  On response = wait for the expected "
            "reply.  Response + delay = wait for the reply, then also wait the delay.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._sync_enabled()

    def _sync_enabled(self) -> None:
        mode = self.advance.currentData()
        wants_response = mode != ADVANCE_TIME
        self.expect.setEnabled(wants_response)
        self.fail_on.setEnabled(wants_response)
        self.expect_fmt.setEnabled(wants_response)
        self.timeout.setEnabled(wants_response)
        self.on_timeout.setEnabled(wants_response)
        self.max_retries.setEnabled(wants_response)
        self.beep_on_match.setEnabled(wants_response)

    def result_step(self) -> Step:
        return Step(
            name=self.name.text().strip() or "Step",
            data=self.data.toPlainText(),
            fmt=self.fmt.currentText(),
            line_ending=self.line_ending.currentText(),
            advance=self.advance.currentData(),
            delay_ms=self.delay.value(),
            expect=self.expect.text(),
            expect_fmt=self.expect_fmt.currentText(),
            timeout_ms=self.timeout.value(),
            on_timeout=self.on_timeout.currentData(),
            max_retries=self.max_retries.value(),
            beep_on_match=self.beep_on_match.isChecked(),
            fail_on=self.fail_on.text(),
        )


class SequenceEditorDialog(QDialog):
    """Edit a named sequence (name + step list)."""

    def __init__(self, parent=None, sequence: NamedSequence | None = None):
        super().__init__(parent)
        self.setWindowTitle("Sequence")
        self.setMinimumSize(520, 420)
        sequence = sequence or NamedSequence()
        self._building_table = False
        self.steps: list[Step] = [Step.from_dict(s.to_dict()) for s in sequence.steps]

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(sequence.name)
        self.name_edit.setPlaceholderText("e.g. Device init")
        form.addRow("Name", self.name_edit)
        layout.addLayout(form)

        hint = QLabel("Steps run top to bottom. Double-click a row to edit.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        layout.addWidget(hint)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["On", "Name", "Advance", "Delay/TO", "Expect"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(lambda _: self._edit_step())
        self.table.itemChanged.connect(self._on_item_changed)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in (2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        btn_row = QGridLayout()
        for i, (label, slot) in enumerate([
            ("Add", self._add_step), ("Edit", self._edit_step),
            ("Duplicate", self._duplicate_step), ("Remove", self._remove_step),
            ("↑ Up", self._move_up), ("↓ Down", self._move_down),
        ]):
            b = QPushButton(label)
            b.clicked.connect(slot)
            btn_row.addWidget(b, i // 3, i % 3)
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._rebuild_table()

    def _rebuild_table(self) -> None:
        self._building_table = True
        self.table.setRowCount(len(self.steps))
        for r, step in enumerate(self.steps):
            on = QTableWidgetItem()
            on.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            on.setCheckState(Qt.CheckState.Checked if step.enabled else Qt.CheckState.Unchecked)
            self.table.setItem(r, 0, on)
            self.table.setItem(r, 1, QTableWidgetItem(step.name))
            self.table.setItem(r, 2, QTableWidgetItem(ADVANCE_LABELS.get(step.advance, step.advance)))
            to = f"{step.delay_ms} ms" if step.advance == "time" else f"{step.timeout_ms} ms"
            self.table.setItem(r, 3, QTableWidgetItem(to))
            self.table.setItem(r, 4, QTableWidgetItem(step.expect or "—"))
        self._building_table = False

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._building_table or item.column() != 0:
            return
        row = item.row()
        if 0 <= row < len(self.steps):
            self.steps[row].enabled = item.checkState() == Qt.CheckState.Checked

    def _current_row(self) -> int:
        return self.table.currentRow()

    def _add_step(self) -> None:
        dlg = StepDialog(self)
        if dlg.exec():
            self.steps.append(dlg.result_step())
            self._rebuild_table()

    def _edit_step(self) -> None:
        row = self._current_row()
        if row < 0 or row >= len(self.steps):
            return
        dlg = StepDialog(self, self.steps[row])
        if dlg.exec():
            self.steps[row] = dlg.result_step()
            self._rebuild_table()
            self.table.selectRow(row)

    def _duplicate_step(self) -> None:
        row = self._current_row()
        if row < 0 or row >= len(self.steps):
            return
        self.steps.insert(row + 1, Step.from_dict(self.steps[row].to_dict()))
        self._rebuild_table()
        self.table.selectRow(row + 1)

    def _remove_step(self) -> None:
        row = self._current_row()
        if row < 0 or row >= len(self.steps):
            return
        del self.steps[row]
        self._rebuild_table()

    def _move_up(self) -> None:
        row = self._current_row()
        if row <= 0:
            return
        self.steps[row - 1], self.steps[row] = self.steps[row], self.steps[row - 1]
        self._rebuild_table()
        self.table.selectRow(row - 1)

    def _move_down(self) -> None:
        row = self._current_row()
        if row < 0 or row >= len(self.steps) - 1:
            return
        self.steps[row + 1], self.steps[row] = self.steps[row], self.steps[row + 1]
        self._rebuild_table()
        self.table.selectRow(row + 1)

    def result_sequence(self) -> NamedSequence:
        name = self.name_edit.text().strip() or "Sequence"
        return NamedSequence(name=name, steps=list(self.steps))
