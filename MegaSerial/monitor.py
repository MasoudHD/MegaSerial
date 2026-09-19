"""A single monitor pane: its own format + bytes-per-row selector over a shared
data stream. Two of these are used side by side for the split view."""
from __future__ import annotations

import csv
import html
import re
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QFont, QTextOption
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPlainTextEdit,
)

from . import utils
from .panel_protocol import panel_event
from .panel_model import GENERAL

DISPLAY_FORMATS = ["ASCII", "HEX", "Binary", "Hexdump"]
BYTES_PER_ROW = ["8", "16", "32", "64"]
_ROW_FORMATS = {"HEX", "Binary", "Hexdump"}

# Presentation only. Events keep the semantic "rx"/"tx" direction values that
# filtering, CSV export and project files rely on.
# Request text glyphs so the foreground color applies instead of emoji artwork.
DIRECTION_SYMBOLS = {"rx": "⬅\ufe0e", "tx": "➡\ufe0e"}
DIRECTION_COLORS = {"rx": "#dc2626", "tx": "#16a34a"}


def direction_symbol(direction: str) -> str:
    """Arrow shown for an event direction; anything but ``tx`` reads as incoming."""
    return DIRECTION_SYMBOLS.get(direction, DIRECTION_SYMBOLS["rx"])

MIN_FONT_POINT_SIZE = 6
MAX_FONT_POINT_SIZE = 32
DEFAULT_FONT_POINT_SIZE = 11


def clamp_font_point_size(size) -> int:
    """Coerce *size* to an int inside the supported monitor font range."""
    try:
        value = int(size)
    except (TypeError, ValueError):
        return DEFAULT_FONT_POINT_SIZE
    return max(MIN_FONT_POINT_SIZE, min(MAX_FONT_POINT_SIZE, value))


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


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "index", "timestamp", "elapsed_ms", "event_type", "direction",
    "data_format", "data", "text", "log_kind", "message",
]
CSV_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
# Excel only auto-detects UTF-8 in a CSV when a BOM is present.
CSV_ENCODING = "utf-8-sig"


def _csv_text(ev: dict) -> str:
    """One-line rendering of the text the monitor filter matches against."""
    text = event_text(ev)
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def _csv_timestamp(ev: dict) -> str:
    ts = ev.get("ts")
    if not isinstance(ts, datetime):
        return ""
    return ts.strftime(CSV_TIMESTAMP_FORMAT)[:-3]


def event_csv_row(ev: dict, index: int, prev_ts: datetime | None) -> list:
    """Build one CSV row from a stored monitor event.

    Fields an event does not carry are left empty rather than invented.
    """
    ts = ev.get("ts")
    elapsed = ""
    if isinstance(ts, datetime) and isinstance(prev_ts, datetime):
        elapsed = int((ts - prev_ts).total_seconds() * 1000)

    row = {
        "index": index,
        "timestamp": _csv_timestamp(ev),
        "elapsed_ms": elapsed,
        "event_type": ev.get("type", ""),
        "text": _csv_text(ev),
    }
    if ev.get("type") == "data":
        row.update({
            "direction": ev.get("dir", ""),
            "data_format": "hex",
            "data": utils.to_hex(ev.get("data", b"") or b""),
        })
    elif ev.get("type") == "log":
        row.update({
            "log_kind": ev.get("kind", "info"),
            "message": ev.get("msg", ""),
        })
    return [row.get(column, "") for column in CSV_COLUMNS]


def events_to_csv_rows(events, panel_titles: dict | None = None) -> list[list]:
    """Return the header row followed by one row per event."""
    rows = [list(CSV_COLUMNS) + (["panel_id", "panel_title"] if panel_titles is not None else [])]
    prev_ts = None
    for index, ev in enumerate(events, start=1):
        row = event_csv_row(ev, index, prev_ts)
        if panel_titles is not None:
            ident = ev.get("panel_id") or GENERAL
            row[CSV_COLUMNS.index("text")] = _csv_text(panel_event(ev))
            row.extend([ident, panel_titles.get(ident, "General" if ident == GENERAL else "")])
        rows.append(row)
        if isinstance(ev.get("ts"), datetime):
            prev_ts = ev["ts"]
    return rows


def write_events_csv(path: str | Path, events, panel_titles: dict | None = None) -> int:
    """Write *events* as CSV and return the number of exported events."""
    rows = events_to_csv_rows(events, panel_titles)
    with open(path, "w", encoding=CSV_ENCODING, newline="") as fh:
        csv.writer(fh).writerows(rows)
    return len(rows) - 1


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
        arrow_color = DIRECTION_COLORS["tx" if direction == "tx" else "rx"]
        prefix += f'<span style="color:{arrow_color}">{direction_symbol(direction)} </span>'
    body = (ev["data"].decode("utf-8", errors="replace")
            if fmt == "ASCII" and opts.get("unicode_text")
            else utils.format_output(ev["data"], fmt, bytes_per_row))
    if fmt == "ASCII":
        # Drop carriage returns and the trailing newline so line-oriented text
        # (e.g. AT commands) shows as one clean line per entry.
        body = body.replace("\r", "").rstrip("\n")
    body_html = html.escape(body).replace("\n", "<br>")
    return f'{prefix}<span style="color:{color}">{body_html}</span>'


class MonitorView(QWidget):
    def __init__(self, fmt: str = "ASCII", bytes_per_row: int = 16,
                 on_settings_changed=None, max_blocks: int = 6000,
                 font_point_size: int = DEFAULT_FONT_POINT_SIZE,
                 on_zoom_requested=None):
        super().__init__()
        self._on_change = on_settings_changed
        self._on_zoom = on_zoom_requested
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
        mono.setPointSize(clamp_font_point_size(font_point_size))
        self.edit.setFont(mono)
        self.edit.viewport().installEventFilter(self)
        v.addWidget(self.edit, 1)

        self._sync_row_enabled()

    # -- zoom --------------------------------------------------------------
    @property
    def font_point_size(self) -> int:
        return clamp_font_point_size(self.edit.font().pointSize())

    def set_font_point_size(self, size) -> int:
        """Apply a clamped presentation font size and return what was applied."""
        applied = clamp_font_point_size(size)
        font = self.edit.font()
        font.setPointSize(applied)
        self.edit.setFont(font)
        return applied

    def zoom_by(self, steps: int) -> None:
        """Handle a zoom gesture, delegating to the owner when one is set."""
        if self._on_zoom is not None:
            self._on_zoom(steps)
        else:
            self.set_font_point_size(self.font_point_size + steps)

    def eventFilter(self, obj, event):
        # Ctrl+wheel zooms; a plain wheel falls through to normal scrolling.
        if obj is self.edit.viewport() and event.type() == QEvent.Type.Wheel:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta:
                    self.zoom_by(1 if delta > 0 else -1)
                return True
        return super().eventFilter(obj, event)

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
