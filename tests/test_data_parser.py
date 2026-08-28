"""Characterization tests for parsing numeric monitor data into graph points."""
from __future__ import annotations

from datetime import datetime
import unittest

from MegaSerial.data_parser import (
    GRAPH_MODE_AUTO,
    GRAPH_MODE_TIME,
    GRAPH_MODE_XY,
    parse_line,
)


TS = datetime(2024, 1, 2, 3, 4, 5)


class DataParserTests(unittest.TestCase):
    def test_auto_prefers_explicit_xy_pairs(self):
        points = parse_line("x=1.25, y=-2e1", TS, GRAPH_MODE_AUTO)

        self.assertEqual(len(points), 1)
        self.assertEqual((points[0].series, points[0].x, points[0].y, points[0].ts),
                         ("Y", 1.25, -20.0, TS))

    def test_auto_prefers_axis_pair_over_other_labeled_channels(self):
        points = parse_line("temp=23.5 hum:40 x=1 y=2", TS)

        self.assertEqual([(p.series, p.x, p.y) for p in points],
                         [("Y", 1.0, 2.0)])

    def test_time_mode_parses_a_single_number(self):
        points = parse_line("  -3.5e2\r\n", TS, GRAPH_MODE_TIME)

        self.assertEqual([(p.series, p.x, p.y, p.ts) for p in points],
                         [("value", None, -350.0, TS)])

    def test_xy_mode_accepts_comma_or_semicolon_pair(self):
        points = parse_line("1.5; 2.75", TS, GRAPH_MODE_XY)

        self.assertEqual([(p.series, p.x, p.y) for p in points], [("Y", 1.5, 2.75)])

    def test_xy_mode_does_not_parse_space_separated_numeric_pair(self):
        self.assertEqual(parse_line("1.5 2.75", TS, GRAPH_MODE_XY), [])


if __name__ == "__main__":
    unittest.main()
