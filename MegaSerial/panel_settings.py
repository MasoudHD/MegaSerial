"""Per-window settings dialog, independent of event retention implementation."""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QSpinBox, QLabel, QDialogButtonBox
from .event_history import MAX_CAPACITY


class PanelSettingsDialog(QDialog):
    def __init__(self, ident, title, capacity, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Window settings — {title} ({ident})")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.capacity = QSpinBox()
        self.capacity.setRange(1, MAX_CAPACITY)
        self.capacity.setGroupSeparatorShown(True)
        self.capacity.setValue(capacity)
        form.addRow("Message capacity", self.capacity)
        layout.addLayout(form)
        label = QLabel("Counts messages, not lines. Reducing capacity discards the oldest excess messages.\n"
                       "Larger capacities use more memory. This setting is saved with the project.")
        label.setWordWrap(True)
        layout.addWidget(label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
