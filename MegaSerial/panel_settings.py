"""Extensible per-window settings dialog."""
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QSpinBox, QLabel,
    QDialogButtonBox, QWidget, QComboBox, QPushButton, QColorDialog, QCheckBox, QGroupBox,
)
from .event_history import MAX_CAPACITY
from .panel_appearance import normalize_appearance


class ColorControl(QWidget):
    def __init__(self, value=None):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox()
        self.combo.addItem('Use default', None)
        for name, color in [('Black', '#000000'), ('White', '#ffffff'), ('Dark gray', '#202020'),
                            ('Light gray', '#eeeeee'), ('Red', '#ff0000'), ('Green', '#00aa00'),
                            ('Blue', '#3399ff'), ('Yellow', '#ffff00'), ('Purple', '#bb66dd')]:
            self._add_color(name, color)
        self.set_color(value)
        row.addWidget(self.combo, 1)
        choose = QPushButton('Choose color…')
        choose.clicked.connect(self.choose_color)
        row.addWidget(choose)

    def _add_color(self, name, color):
        swatch = QPixmap(18, 18)
        swatch.fill(QColor(color))
        self.combo.addItem(QIcon(swatch), name, color)

    def set_color(self, color):
        index = self.combo.findData(color)
        if index < 0:
            self._add_color(color, color)
            index = self.combo.count() - 1
        self.combo.setCurrentIndex(index)

    def value(self):
        return self.combo.currentData()

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.value() or '#ffffff'), self, 'Choose color')
        if color.isValid():
            self.set_color(color.name())


class PanelSettingsDialog(QDialog):
    def __init__(self, ident, title, capacity, parent=None, appearance=None):
        super().__init__(parent)
        self.setWindowTitle(f"Window settings — {title} ({ident})")
        appearance = normalize_appearance(appearance)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.capacity = QSpinBox()
        self.capacity.setRange(1, MAX_CAPACITY)
        self.capacity.setGroupSeparatorShown(True)
        self.capacity.setValue(capacity)
        form.addRow('Message capacity', self.capacity)
        layout.addLayout(form)
        label = QLabel('Reducing capacity discards the oldest excess messages. Larger capacities use more memory.')
        label.setWordWrap(True)
        layout.addWidget(label)
        group = QGroupBox('Appearance')
        colors = QFormLayout(group)
        self.colors = {}
        for key, title in [('background', 'Background'), ('text', 'Message text'),
                           ('title', 'Title text'), ('rx', 'RX icon'), ('tx', 'TX icon')]:
            control = ColorControl(appearance.get(key))
            self.colors[key] = control
            colors.addRow(title, control)
        layout.addWidget(group)
        group = QGroupBox('Display')
        display = QFormLayout(group)
        self.overrides = {}
        for key, title in [('show_ts', 'Timestamps'), ('show_linenum', 'Line numbers')]:
            control = QComboBox()
            for label, value in [('Use global setting', None), ('Show', True), ('Hide', False)]:
                control.addItem(label, value)
            control.setCurrentIndex(control.findData(appearance.get(key)))
            self.overrides[key] = control
            display.addRow(title, control)
        self.show_counter = QCheckBox('Show received-message counter')
        self.show_counter.setChecked(appearance.get('show_counter', True))
        display.addRow(self.show_counter)
        layout.addWidget(group)
        note = QLabel('Received counts RX messages since clearing, including messages filtered out or evicted.\n'
                      'Settings apply only to this window and are saved with the project.')
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def appearance(self):
        values = {key: control.value() for key, control in self.colors.items()}
        values.update({key: control.currentData() for key, control in self.overrides.items()})
        values['show_counter'] = self.show_counter.isChecked()
        return normalize_appearance(values)
