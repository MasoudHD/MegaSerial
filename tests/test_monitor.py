"""Characterization tests for non-widget monitor filtering and HTML rendering."""
from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from MegaSerial.monitor import compile_filter, event_matches_filter, event_text, render_html


COLORS = {
    "rx": "#111111",
    "tx": "#222222",
    "info": "#333333",
    "warn": "#444444",
    "error": "#555555",
    "timestamp": "#666666",
    "delay": "#777777",
}
OPTS = {
    "show_ts": True,
    "show_delays": True,
    "show_dir": True,
    "show_linenum": True,
    "autoscroll": False,
    "colors": COLORS,
}
TS = datetime(2024, 1, 2, 3, 4, 5, 123456)


class MonitorFilterTests(unittest.TestCase):
    def test_compile_filter_handles_empty_valid_and_invalid_patterns(self):
        self.assertIsNone(compile_filter(""))
        self.assertIsNone(compile_filter("["))
        regex = compile_filter("hello", case_insensitive=True)
        self.assertIsNotNone(regex)
        self.assertTrue(regex.search("HELLO"))

    def test_event_text_decodes_data_and_returns_log_message(self):
        self.assertEqual(event_text({"type": "data", "data": b"A\xff"}), "A\ufffd")
        self.assertEqual(event_text({"type": "log", "msg": "opened"}), "opened")

    def test_direction_filter_applies_to_data_but_not_log_events(self):
        regex = compile_filter("match")
        self.assertFalse(event_matches_filter(
            {"type": "data", "dir": "tx", "data": b"match"}, regex, "rx"))
        self.assertTrue(event_matches_filter(
            {"type": "data", "dir": "rx", "data": b"match"}, regex, "rx"))
        self.assertTrue(event_matches_filter(
            {"type": "log", "kind": "info", "msg": "match"}, regex, "rx"))


class MonitorRenderingTests(unittest.TestCase):
    def test_render_data_escapes_content_and_strips_ascii_line_ending(self):
        event = {"type": "data", "dir": "rx", "ts": TS, "data": b"<tag>\r\n"}

        rendered = render_html(event, "ASCII", 16, OPTS, line_num=7)

        self.assertIn("    7 ", rendered)
        self.assertIn("03:04:05.123", rendered)
        self.assertIn("\u2190", rendered)
        self.assertIn("&lt;tag&gt;", rendered)
        self.assertNotIn("<tag>", rendered)
        self.assertNotIn("<br>", rendered)

    def test_render_log_includes_delay_timestamp_and_escaped_message(self):
        event = {"type": "log", "kind": "warn", "ts": TS + timedelta(milliseconds=250),
                 "msg": "lost <port>"}

        rendered = render_html(event, "HEX", 16, OPTS, prev_ts=TS, line_num=2)

        self.assertIn("+250 ms", rendered)
        self.assertIn("03:04:05.373", rendered)
        self.assertIn("\u2014 lost &lt;port&gt;", rendered)
        self.assertIn("#444444", rendered)


if __name__ == "__main__":
    unittest.main()
