"""A single monitor pane: its own format + bytes-per-row selector over a shared
data stream. Two of these are used side by side for the split view."""
from __future__ import annotations

import html
import re
from datetime import datetime

from PyQt6.QtGui import QFont, QTextOption
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPlainTextEdit,
)

from . import utils

DISPLAY_FORMATS = ["ASCII", "HEX", "Binary", "Hexdump"]
BYTES_PER_ROW = ["8", "16", "32", "64"]
_ROW_FORMATS = {"HEX", "Binary", "Hexdump"}


def event_text(ev: dict) -> str:
    """Plain text used for regex filtering."""
    if ev.get("type") == "log":
        return ev.get("msg", "")
    if ev.get("type") == "data":
        try:
            return ev["data"].decode("utf-8", errors="replace")
        except (KeyError, AttributeError):
            return ""
    return ""


def compile_filter(pattern: str, case_insensitive: bool = False) -> re.Pattern | None:
    if not pattern:
        return None
    flags = re.MULTILINE
    if case_insensitive:
        flags |= re.IGNORECASE
    try:
        return re.compile(pattern, flags)
    except re.error:
        return None


def event_matches_filter(ev: dict, regex: re.Pattern | None,
                         direction: str = "all") -> bool:
    """Return True if *ev* passes the active filter (or no filter is set)."""
    if regex is None:
        return True
    if ev.get("type") == "data" and direction != "all":
        if direction == "rx" and ev.get("dir") != "rx":
            return False
        if direction == "tx" and ev.get("dir") != "tx":
            return False
    return bool(regex.search(event_text(ev)))


def render_html(ev: dict, fmt: str, bytes_per_row: int, opts: dict,
                prev_ts: datetime | None = None, line_num: int = 0) -> str:
    """Build one HTML block for an event, given a view's format/row settings."""
    colors = opts["colors"]
    prefix = ""
    if opts.get("show_linenum") and line_num > 0:
        prefix += f'<span style="color:{colors["timestamp"]}">{line_num:>5} </span>'
    if opts.get("show_delays") and prev_ts is not None and "ts" in ev:
        delta_ms = int((ev["ts"] - prev_ts).total_seconds() * 1000)
        if delta_ms >= 0:
            prefix += (
                f'<span style="color:{colors["delay"]}">+{delta_ms} ms </span>'
            )
    if opts.get("show_ts"):
        ts = ev["ts"].strftime("%H:%M:%S.%f")[:-3]
        prefix += f'<span style="color:{colors["timestamp"]}">{ts} </span>'

    if ev["type"] == "log":
        color = colors.get(ev.get("kind", "info"), colors["info"])
        return f'{prefix}<span style="color:{color}">— {html.escape(ev["msg"])}</span>'

    direction = ev["dir"]
    color = colors["tx"] if direction == "tx" else colors["rx"]
    if opts.get("show_dir"):
        arrow = "→" if direction == "tx" else "←"
        prefix += f'<span style="color:{color}">{arrow} </span>'
    body = utils.format_output(ev["data"], fmt, bytes_per_row)
    if fmt == "ASCII":
        # Drop carriage returns and the trailing newline so line-oriented text
        # (e.g. AT commands) shows as one clean line per entry.
        body = body.replace("\r", "").rstrip("\n")
    body_html = html.escape(body).replace("\n", "<br>")
    return f'{prefix}<span style="color:{color}">{body_html}</span>'


class MonitorView(QWidget):
    def __init__(self, fmt: str = "ASCII", bytes_per_row: int = 16,
                 on_settings_changed=None, max_blocks: int = 6000):
        super().__init__()
        self._on_change = on_settings_changed
        self._line_counter = 0

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        head = QHBoxLayout()
        head.addWidget(QLabel("View"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(DISPLAY_FORMATS)
        self.format_combo.setCurrentText(fmt)
        self.format_combo.currentTextChanged.connect(self._settings_changed)
        head.addWidget(self.format_combo)
        head.addSpacing(6)
        self.row_label = QLabel("Bytes/row")
        head.addWidget(self.row_label)
        self.row_combo = QComboBox()
        self.row_combo.addItems(BYTES_PER_ROW)
        self.row_combo.setCurrentText(str(bytes_per_row))
        self.row_combo.currentTextChanged.connect(self._settings_changed)
        head.addWidget(self.row_combo)
        head.addStretch(1)
        v.addLayout(head)

        self.edit = QPlainTextEdit()
        self.edit.setReadOnly(True)
        self.edit.setMaximumBlockCount(max_blocks)
        self.edit.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        mono = QFont("Monospace")
        mono.setStyleHint(QFont.StyleHint.TypeWriter)
        mono.setPointSize(11)
        self.edit.setFont(mono)
        v.addWidget(self.edit, 1)

        self._sync_row_enabled()

    # -- settings ----------------------------------------------------------
    def _sync_row_enabled(self) -> None:
        enabled = self.format_combo.currentText() in _ROW_FORMATS
        self.row_combo.setEnabled(enabled)
        self.row_label.setEnabled(enabled)

    def _settings_changed(self, *_):
        self._sync_row_enabled()
        if self._on_change:
            self._on_change(self)

    @property
    def fmt(self) -> str:
        return self.format_combo.currentText()

    @property
    def bytes_per_row(self) -> int:
        try:
            return int(self.row_combo.currentText())
        except ValueError:
            return 16

    # -- rendering ---------------------------------------------------------
    def append_event(self, ev: dict, opts: dict, prev_ts: datetime | None = None) -> None:
        self._line_counter += 1
        self.edit.appendHtml(render_html(ev, self.fmt, self.bytes_per_row, opts, prev_ts, self._line_counter))
        if opts.get("autoscroll"):
            sb = self.edit.verticalScrollBar()
            sb.setValue(sb.maximum())

    def rerender(self, events, opts: dict) -> None:
        self.edit.clear()
        self._line_counter = 0
        fmt = self.fmt
        bpr = self.bytes_per_row
        prev_ts = None
        for ev in events:
            self._line_counter += 1
            self.edit.appendHtml(render_html(ev, fmt, bpr, opts, prev_ts, self._line_counter))
            if "ts" in ev:
                prev_ts = ev["ts"]
        if opts.get("autoscroll"):
            sb = self.edit.verticalScrollBar()
            sb.setValue(sb.maximum())

    def clear(self) -> None:
        self.edit.clear()
        self._line_counter = 0

    def plain_text(self) -> str:
        return self.edit.toPlainText()
