"""Live plot pane for numeric serial data (time series and XY)."""
from __future__ import annotations

import csv
from collections import deque
from datetime import datetime
from pathlib import Path

import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox,
    QPushButton, QCheckBox, QFileDialog, QMessageBox,
)

from .data_parser import (
    GRAPH_MODE_AUTO, GRAPH_MODE_TIME, GRAPH_MODE_XY, GRAPH_MODES, parse_line,
)

_SERIES_COLORS = [
    "#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#a855f7",
    "#06b6d4", "#ec4899", "#84cc16",
]

# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

# One row per plotted point ("long" format). Series keep independent x values,
# so a shared-x wide layout could not represent the data without inventing
# values for the gaps.
GRAPH_CSV_COLUMNS = ["series", "point_index", "x", "y"]
GRAPH_CSV_ENCODING = "utf-8-sig"


def series_csv_rows(series_data) -> list[list]:
    """Header row plus one row per plotted point, in series then plot order.

    *series_data* maps a series name to ``{"x": ..., "y": ...}`` sequences.
    Values are written as Python floats, which round-trip exactly.
    """
    rows = [list(GRAPH_CSV_COLUMNS)]
    for name, points in series_data.items():
        for index, (x, y) in enumerate(zip(points["x"], points["y"]), start=1):
            rows.append([name, index, x, y])
    return rows


def write_series_csv(path: str | Path, series_data) -> int:
    """Write the plotted points as CSV and return the number of points."""
    rows = series_csv_rows(series_data)
    with open(path, "w", encoding=GRAPH_CSV_ENCODING, newline="") as fh:
        csv.writer(fh).writerows(rows)
    return len(rows) - 1


class GraphPanel(QWidget):
    """Bottom pane: live pyqtgraph plot fed from RX (or TX) data events."""

    def __init__(self):
        super().__init__()
        self._mode = GRAPH_MODE_AUTO
        self._max_points = 1000
        self._rx_only = True
        self._auto_scroll = True
        self._t0: datetime | None = None
        self._sample_idx = 0
        self._series_data: dict[str, dict] = {}
        self._curves: dict[str, pg.PlotDataItem] = {}
        self._color_i = 0

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(4)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Graph"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Auto", GRAPH_MODE_AUTO)
        self.mode_combo.addItem("Time series", GRAPH_MODE_TIME)
        self.mode_combo.addItem("XY pairs", GRAPH_MODE_XY)
        self.mode_combo.currentIndexChanged.connect(self._on_settings_changed)
        bar.addWidget(self.mode_combo)

        bar.addWidget(QLabel("Max pts"))
        self.max_pts = QSpinBox()
        self.max_pts.setRange(50, 50_000)
        self.max_pts.setValue(self._max_points)
        self.max_pts.valueChanged.connect(self._on_max_points)
        bar.addWidget(self.max_pts)

        self.rx_only_check = QCheckBox("RX only")
        self.rx_only_check.setChecked(True)
        self.rx_only_check.toggled.connect(self._on_settings_changed)
        bar.addWidget(self.rx_only_check)

        self.autoscroll_check = QCheckBox("Autoscroll")
        self.autoscroll_check.setChecked(True)
        self.autoscroll_check.toggled.connect(self._on_settings_changed)
        bar.addWidget(self.autoscroll_check)

        self.clear_btn = QPushButton("Clear graph")
        self.clear_btn.clicked.connect(self.clear)
        bar.addWidget(self.clear_btn)

        self.export_image_btn = QPushButton("Save image")
        self.export_image_btn.setToolTip("Save the plotted graph as a PNG image")
        self.export_image_btn.clicked.connect(self.export_image_dialog)
        bar.addWidget(self.export_image_btn)

        self.export_csv_btn = QPushButton("Export CSV")
        self.export_csv_btn.setToolTip("Export the plotted data points as CSV")
        self.export_csv_btn.clicked.connect(self.export_csv_dialog)
        bar.addWidget(self.export_csv_btn)
        bar.addStretch(1)

        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: palette(mid);")
        bar.addWidget(self.stats_label)
        v.addLayout(bar)

        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.addLegend(offset=(10, 10))
        self.plot.setLabel("bottom", "Time (s)" if self._mode != GRAPH_MODE_XY else "X")
        self.plot.setLabel("left", "Value")
        v.addWidget(self.plot, 1)

        self.apply_theme("dark")

    # ------------------------------------------------------------------ API
    def apply_theme(self, mode: str) -> None:
        if mode == "light":
            pg.setConfigOption("background", "w")
            pg.setConfigOption("foreground", "k")
        else:
            pg.setConfigOption("background", "#17181c")
            pg.setConfigOption("foreground", "#e6e6e6")
        self.plot.getPlotItem().getViewBox().update()

    def settings_dict(self) -> dict:
        return {
            "graph_mode": self.mode_combo.currentData(),
            "graph_max_points": self.max_pts.value(),
            "graph_rx_only": self.rx_only_check.isChecked(),
            "graph_autoscroll": self.autoscroll_check.isChecked(),
        }

    def load_settings(self, cfg: dict) -> None:
        mode = cfg.get("graph_mode", GRAPH_MODE_AUTO)
        idx = self.mode_combo.findData(mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
        self.max_pts.setValue(int(cfg.get("graph_max_points", 1000)))
        self.rx_only_check.setChecked(cfg.get("graph_rx_only", True))
        self.autoscroll_check.setChecked(cfg.get("graph_autoscroll", True))
        self._sync_mode()

    def replay_events(self, events, *, text_filter=None) -> None:
        """Rebuild plot from stored monitor events."""
        self.clear()
        for ev in events:
            if text_filter and not text_filter(ev):
                continue
            self.feed_event(ev)

    def feed_event(self, ev: dict) -> None:
        if ev.get("type") != "data":
            return
        if self._rx_only and ev.get("dir") != "rx":
            return
        try:
            text = ev["data"].decode("utf-8", errors="replace")
        except (KeyError, AttributeError):
            return
        ts = ev.get("ts") or datetime.now()
        for pt in parse_line(text, ts, self._mode):
            self._add_point(pt)

    def clear(self) -> None:
        self._t0 = None
        self._sample_idx = 0
        self._series_data.clear()
        self._curves.clear()
        self._color_i = 0
        self.plot.clear()
        self.plot.addLegend(offset=(10, 10))
        self.stats_label.setText("")

    # -------------------------------------------------------------- exporting
    def series_snapshot(self) -> dict[str, dict[str, list]]:
        """Copy of the plotted points, so exporting cannot disturb live data."""
        return {name: {"x": list(points["x"]), "y": list(points["y"])}
                for name, points in self._series_data.items()}

    def csv_rows(self) -> list[list]:
        return series_csv_rows(self.series_snapshot())

    def export_csv(self, path: str | Path) -> int:
        return write_series_csv(path, self.series_snapshot())

    def export_image(self, path: str | Path) -> None:
        """Save the plot area, as currently displayed, to an image file."""
        from pyqtgraph.exporters import ImageExporter

        ImageExporter(self.plot.getPlotItem()).export(str(path))

    def has_data(self) -> bool:
        return any(points["y"] for points in self._series_data.values())

    def export_csv_dialog(self) -> None:
        if not self._warn_if_empty():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export graph CSV", "graph.csv",
                                              "CSV files (*.csv);;All files (*)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            count = self.export_csv(path)
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        self.stats_label.setText(f"Exported {count} points")

    def export_image_dialog(self) -> None:
        if not self._warn_if_empty():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save graph image", "graph.png",
            "PNG image (*.png);;All files (*)")
        if not path:
            return
        if not Path(path).suffix:
            path += ".png"
        try:
            self.export_image(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Save failed", str(exc))

    def _warn_if_empty(self) -> bool:
        if self.has_data():
            return True
        QMessageBox.information(self, "Empty graph",
                                "There is no plotted data to export yet.")
        return False

    # ----------------------------------------------------------------- internals
    def _on_settings_changed(self, *_args) -> None:
        self._rx_only = self.rx_only_check.isChecked()
        self._auto_scroll = self.autoscroll_check.isChecked()
        self._sync_mode()

    def _on_max_points(self, val: int) -> None:
        self._max_points = val
        for name, d in self._series_data.items():
            while len(d["x"]) > self._max_points:
                d["x"].popleft()
                d["y"].popleft()
            if name in self._curves:
                self._curves[name].setData(list(d["x"]), list(d["y"]))

    def _sync_mode(self) -> None:
        self._mode = self.mode_combo.currentData() or GRAPH_MODE_AUTO
        self.plot.setLabel(
            "bottom", "X" if self._mode == GRAPH_MODE_XY else "Time (s)")

    def _next_color(self) -> str:
        c = _SERIES_COLORS[self._color_i % len(_SERIES_COLORS)]
        self._color_i += 1
        return c

    def _x_for_time_series(self, pt) -> float:
        if pt.x is not None:
            return pt.x
        if pt.ts is not None:
            if self._t0 is None:
                self._t0 = pt.ts
            return (pt.ts - self._t0).total_seconds()
        self._sample_idx += 1
        return float(self._sample_idx)

    def _add_point(self, pt) -> None:
        name = pt.series
        if name not in self._series_data:
            self._series_data[name] = {"x": deque(maxlen=self._max_points),
                                       "y": deque(maxlen=self._max_points)}
            pen = pg.mkPen(color=self._next_color(), width=2)
            self._curves[name] = self.plot.plot([], [], name=name, pen=pen,
                                                symbol="o", symbolSize=4)

        if self._mode == GRAPH_MODE_XY and pt.x is not None:
            x_val = pt.x
        else:
            x_val = self._x_for_time_series(pt)

        d = self._series_data[name]
        d["x"].append(x_val)
        d["y"].append(pt.y)
        xs, ys = list(d["x"]), list(d["y"])
        self._curves[name].setData(xs, ys)

        if self._auto_scroll and xs:
            xmin, xmax = min(xs), max(xs)
            pad = max((xmax - xmin) * 0.05, 0.5)
            self.plot.setXRange(xmin - pad, xmax + pad, padding=0)

        total = sum(len(d["y"]) for d in self._series_data.values())
        self.stats_label.setText(
            f"{len(self._series_data)} series · {total} points")
