"""Tests for graph CSV/image export.

The CSV row builder is a pure function over the graph's series data, so the
structural tests need no widgets or file dialogs.
"""
from __future__ import annotations

import csv
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from MegaSerial.graph_panel import (
        GRAPH_CSV_COLUMNS, GRAPH_CSV_ENCODING, series_csv_rows, write_series_csv,
    )
except Exception as exc:  # noqa: BLE001 - pyqtgraph/Qt unavailable
    raise unittest.SkipTest(f"Graph panel unavailable: {exc}")

TS = datetime(2024, 1, 2, 3, 4, 5)


class GraphCsvRowTests(unittest.TestCase):
    def test_an_empty_graph_produces_only_the_header(self):
        self.assertEqual(series_csv_rows({}), [GRAPH_CSV_COLUMNS])

    def test_a_series_with_no_points_produces_only_the_header(self):
        self.assertEqual(series_csv_rows({"temp": {"x": [], "y": []}}),
                         [GRAPH_CSV_COLUMNS])

    def test_points_are_numbered_per_series_and_keep_plot_order(self):
        rows = series_csv_rows({"temp": {"x": [0.0, 1.0, 2.0], "y": [20.5, 21.0, 21.5]}})

        self.assertEqual(rows[0], GRAPH_CSV_COLUMNS)
        self.assertEqual(rows[1:], [
            ["temp", 1, 0.0, 20.5],
            ["temp", 2, 1.0, 21.0],
            ["temp", 3, 2.0, 21.5],
        ])

    def test_multiple_series_are_exported_and_restart_their_indices(self):
        rows = series_csv_rows({
            "temp": {"x": [0.0, 1.0], "y": [20.0, 21.0]},
            "hum": {"x": [0.0], "y": [55.0]},
        })

        self.assertEqual([row[0] for row in rows[1:]], ["temp", "temp", "hum"])
        self.assertEqual([row[1] for row in rows[1:]], [1, 2, 1])

    def test_series_of_different_lengths_are_not_padded(self):
        rows = series_csv_rows({
            "a": {"x": [0.0, 1.0, 2.0], "y": [1.0, 2.0, 3.0]},
            "b": {"x": [0.0], "y": [9.0]},
        })

        self.assertEqual(len(rows), 5)  # header + 3 + 1

    def test_the_source_series_data_is_not_modified_by_exporting(self):
        data = {"temp": {"x": [0.0, 1.0], "y": [20.0, 21.0]}}
        before = {"temp": {"x": [0.0, 1.0], "y": [20.0, 21.0]}}

        series_csv_rows(data)

        self.assertEqual(data, before)


class GraphCsvFileTests(unittest.TestCase):
    def _write_and_read(self, series_data) -> list[list[str]]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graph.csv"
            self.written = write_series_csv(path, series_data)
            with open(path, "r", encoding=GRAPH_CSV_ENCODING, newline="") as fh:
                return list(csv.reader(fh))

    def test_the_file_starts_with_the_header_even_when_empty(self):
        rows = self._write_and_read({})

        self.assertEqual(rows, [GRAPH_CSV_COLUMNS])
        self.assertEqual(self.written, 0)

    def test_numeric_precision_survives_the_round_trip(self):
        values = [0.1, 1e-9, -273.15, 1234567.891234, 2.5e12]
        rows = self._write_and_read({"v": {"x": list(range(len(values))), "y": values}})

        exported = [float(row[GRAPH_CSV_COLUMNS.index("y")]) for row in rows[1:]]
        self.assertEqual(exported, values)

    def test_series_names_with_commas_and_unicode_round_trip(self):
        name = 'temp, "outer" °C'
        rows = self._write_and_read({name: {"x": [0.0], "y": [1.0]}})

        self.assertEqual(rows[1][0], name)


class GraphPanelExportTests(unittest.TestCase):
    """End-to-end checks against a real panel fed with parsed serial lines."""

    @classmethod
    def setUpClass(cls):
        try:
            from PyQt6.QtWidgets import QApplication

            cls.app = QApplication.instance() or QApplication([])
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"Qt widgets unavailable: {exc}")

    def setUp(self):
        from MegaSerial.graph_panel import GraphPanel

        self.panel = GraphPanel()
        self.panel.resize(600, 300)
        self.addCleanup(self.panel.deleteLater)
        self.directory = Path(tempfile.mkdtemp())

    def _feed(self, count: int = 5) -> None:
        for i in range(count):
            self.panel.feed_event({
                "type": "data", "dir": "rx", "ts": TS + timedelta(seconds=i),
                "data": f"temp:{20 + i} hum:{50 - i}".encode(),
            })

    def test_an_empty_panel_reports_no_data(self):
        self.assertFalse(self.panel.has_data())
        self.assertEqual(self.panel.csv_rows(), [GRAPH_CSV_COLUMNS])

    def test_exported_rows_match_the_plotted_series(self):
        self._feed(3)

        rows = self.panel.csv_rows()

        self.assertTrue(self.panel.has_data())
        self.assertEqual(len(rows), 1 + 6)   # two series, three points each
        self.assertEqual({row[0] for row in rows[1:]}, {"temp", "hum"})
        temp_y = [row[3] for row in rows[1:] if row[0] == "temp"]
        self.assertEqual(temp_y, [20.0, 21.0, 22.0])

    def test_exporting_does_not_change_the_live_graph(self):
        self._feed(4)
        before = self.panel.csv_rows()

        self.panel.export_csv(self.directory / "graph.csv")
        self.panel.export_image(self.directory / "graph.png")

        self.assertEqual(self.panel.csv_rows(), before)
        self.assertTrue(self.panel.has_data())

    def test_image_export_writes_a_png(self):
        self._feed(5)
        path = self.directory / "graph.png"

        self.panel.export_image(path)

        self.assertTrue(path.exists())
        self.assertEqual(path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
