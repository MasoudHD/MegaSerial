"""About and donation dialogs — content is loaded from ``resources/about.md``."""
from __future__ import annotations

import re
import threading

from PyQt6.QtCore import Qt, QTimer, QUrl, QObject, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from . import __app_name__, __version__
from .icons import resource_path
from .remote_config import donate_links_from_config, load_app_config, load_bundled_config


def _strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _read_about_source() -> str:
    path = resource_path("resources", "about.md")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = f"# {__app_name__}\n\n**Version {__version__}**\n"
    text = text.replace("{{version}}", __version__)
    return _strip_html_comments(text)


def _expand_resource_images(markdown: str) -> str:
    """Turn ``![](app_icon.png)`` into a local file URL Qt can display."""

    def repl(match: re.Match[str]) -> str:
        alt, src = match.group(1), match.group(2).strip()
        if src.startswith(("http://", "https://", "file:")):
            return match.group(0)
        parts = src.split("/")
        resolved = resource_path("resources", *parts)
        if not resolved.is_file():
            return match.group(0)
        url = QUrl.fromLocalFile(str(resolved)).toString()
        return f"![{alt}]({url})"

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl, markdown)


def load_about_markdown() -> str:
    return _expand_resource_images(_read_about_source())


def load_donation_section() -> tuple[str, str]:
    """Return ``(title, description markdown)`` from the ``## Donation`` section in about.md."""
    text = _read_about_source()
    for heading in re.finditer(r"^##\s+(.+?)\s*$", text, re.MULTILINE):
        title = heading.group(1).strip()
        if title.lower() != "donation":
            continue
        start = heading.end()
        rest = text[start:].lstrip("\n")
        next_heading = re.search(r"^##\s+", rest, re.MULTILINE)
        body = rest[: next_heading.start()] if next_heading else rest
        return title, _expand_resource_images(body.strip())
    return "Donation", ""


class _ConfigSignals(QObject):
    loaded = pyqtSignal(dict)


def _center_on_screen(dialog: QDialog) -> None:
    screen = QApplication.primaryScreen()
    if screen is None:
        return
    frame = dialog.frameGeometry()
    frame.moveCenter(screen.availableGeometry().center())
    dialog.move(frame.topLeft())


class DonationButtonsWidget(QWidget):
    """Donation buttons loaded dynamically from the remote gist."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 4, 12, 0)
        self._layout.setSpacing(8)
        self._config_signals = _ConfigSignals()
        self._config_signals.loaded.connect(
            self._on_remote_config,
            Qt.ConnectionType.QueuedConnection,
        )
        self._show_message("Loading donation links…")
        QTimer.singleShot(0, self._fetch_remote_config)

    def _fetch_remote_config(self) -> None:
        signals = self._config_signals

        def work() -> None:
            signals.loaded.emit(load_app_config())

        threading.Thread(target=work, daemon=True).start()

    def _clear_row(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _show_message(self, message: str) -> None:
        self._clear_row()
        label = QLabel(message)
        label.setStyleSheet("color: palette(mid);")
        self._layout.addWidget(label)
        self._layout.addStretch(1)

    def set_links(self, links: list[tuple[str, str]]) -> None:
        self._clear_row()
        if not links:
            self._show_message("Donation links are not available right now.")
            return
        for name, url in links:
            btn = QPushButton(name)
            btn.setToolTip(url)
            btn.clicked.connect(lambda _checked=False, link=url: QDesktopServices.openUrl(QUrl(link)))
            self._layout.addWidget(btn)
        self._layout.addStretch(1)

    def _on_remote_config(self, config: dict) -> None:
        links = donate_links_from_config(config)
        if not links:
            links = donate_links_from_config(load_bundled_config())
        self.set_links(links)


class DonationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        title, description = load_donation_section()
        self.setWindowTitle(title)
        self.setMinimumWidth(440)

        heading = QLabel(title)
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        heading.setFont(font)

        self._body = QTextBrowser()
        self._body.setOpenExternalLinks(True)
        self._body.setFrameShape(QFrame.Shape.NoFrame)
        self._body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        if description:
            self._body.setMarkdown(description)
        else:
            self._body.setPlainText("")

        self._donation_buttons = DonationButtonsWidget()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(heading, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._body, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._donation_buttons, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(buttons)

        QTimer.singleShot(0, self._fit_to_content)

    def _fit_to_content(self) -> None:
        if not self._body.toPlainText() and not self._body.document().toRawText():
            self._body.setFixedHeight(0)
            self.adjustSize()
            return
        doc = self._body.document()
        doc.setTextWidth(max(400, self._body.viewport().width()))
        height = int(doc.size().height()) + 8
        self._body.setFixedHeight(max(40, height))
        self.adjustSize()
        _center_on_screen(self)


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {__app_name__}")
        self.setMinimumWidth(440)

        self._body = QTextBrowser()
        self._body.setOpenExternalLinks(True)
        self._body.setFrameShape(QFrame.Shape.NoFrame)
        self._body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body.setMarkdown(load_about_markdown())

        self._donation_buttons = DonationButtonsWidget()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self._body, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._donation_buttons, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(buttons)

        QTimer.singleShot(0, self._fit_to_content)

    def _fit_to_content(self) -> None:
        doc = self._body.document()
        doc.setTextWidth(max(400, self._body.viewport().width()))
        height = int(doc.size().height()) + 8
        self._body.setFixedHeight(max(120, height))
        self.adjustSize()
        _center_on_screen(self)
