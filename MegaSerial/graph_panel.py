"""Live plot pane for numeric serial data (time series and XY)."""
from __future__ import annotations

from collections import deque
from datetime import datetime

import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox,
    QPushButton, QCheckBox,
)

from .data_parser import (
    GRAPH_MODE_AUTO, GRAPH_MODE_TIME, GRAPH_MODE_XY, GRAPH_MODES, parse_line,
)

_SERIES_COLORS = [
    "#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#a855f7",
    "#06b6d4", "#ec4899", "#84cc16",
]


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
