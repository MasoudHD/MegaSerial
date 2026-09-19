"""Characterization tests for non-widget monitor filtering and HTML rendering."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from MegaSerial.monitor import (
    CSV_COLUMNS, CSV_ENCODING, DEFAULT_FONT_POINT_SIZE, MAX_FONT_POINT_SIZE,
    MIN_FONT_POINT_SIZE, clamp_font_point_size, compile_filter, event_matches_filter,
    event_text, events_to_csv_rows, render_html, write_events_csv,
)


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


class MonitorCsvExportTests(unittest.TestCase):
    def _rows(self, events) -> list[dict]:
        rows = events_to_csv_rows(events)
        self.assertEqual(rows[0], CSV_COLUMNS)
        return [dict(zip(CSV_COLUMNS, row)) for row in rows[1:]]

    def _write_and_read(self, events) -> list[list[str]]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "log.csv"
            written = write_events_csv(path, events)
            self.assertEqual(written, len(events))
            with open(path, "r", encoding=CSV_ENCODING, newline="") as fh:
                return list(csv.reader(fh))

    def test_empty_event_collection_exports_only_the_header(self):
        self.assertEqual(events_to_csv_rows([]), [CSV_COLUMNS])
        self.assertEqual(self._write_and_read([]), [CSV_COLUMNS])

    def test_rx_and_tx_rows_carry_direction_hex_data_and_decoded_text(self):
        rows = self._rows([
            {"type": "data", "dir": "rx", "ts": TS, "data": b"OK\r\n"},
            {"type": "data", "dir": "tx", "ts": TS, "data": b"\x00\xff"},
        ])

        self.assertEqual(rows[0]["event_type"], "data")
        self.assertEqual(rows[0]["direction"], "rx")
        self.assertEqual(rows[0]["data_format"], "hex")
        self.assertEqual(rows[0]["data"], "4F 4B 0D 0A")
        self.assertEqual(rows[0]["text"], "OK\\r\\n")
        self.assertEqual(rows[1]["direction"], "tx")
        self.assertEqual(rows[1]["data"], "00 FF")
        # Log-only columns stay empty for data events.
        self.assertEqual((rows[0]["log_kind"], rows[0]["message"]), ("", ""))

    def test_log_rows_carry_kind_and_message_without_data_columns(self):
        rows = self._rows([{"type": "log", "kind": "error", "ts": TS, "msg": "port lost"}])

        self.assertEqual(rows[0]["event_type"], "log")
        self.assertEqual(rows[0]["log_kind"], "error")
        self.assertEqual(rows[0]["message"], "port lost")
        self.assertEqual(
            (rows[0]["direction"], rows[0]["data_format"], rows[0]["data"]), ("", "", ""))

    def test_index_timestamp_and_elapsed_columns(self):
        rows = self._rows([
            {"type": "log", "kind": "info", "ts": TS, "msg": "first"},
            {"type": "log", "kind": "info", "ts": TS + timedelta(milliseconds=250), "msg": "second"},
            {"type": "log", "kind": "info", "msg": "no timestamp"},
        ])

        self.assertEqual([row["index"] for row in rows], [1, 2, 3])
        self.assertEqual(rows[0]["timestamp"], "2024-01-02 03:04:05.123")
        self.assertEqual(rows[0]["elapsed_ms"], "")
        self.assertEqual(rows[1]["elapsed_ms"], 250)
        self.assertEqual((rows[2]["timestamp"], rows[2]["elapsed_ms"]), ("", ""))

    def test_commas_quotes_and_newlines_survive_a_csv_round_trip(self):
        message = 'a,b "quoted"\nsecond line'
        rows = self._write_and_read([{"type": "log", "kind": "warn", "ts": TS, "msg": message}])

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][CSV_COLUMNS.index("message")], message)

    def test_unicode_survives_in_log_messages_and_rx_payloads(self):
        rows = self._write_and_read([
            {"type": "log", "kind": "info", "ts": TS, "msg": "café ✓ дом"},
            {"type": "data", "dir": "rx", "ts": TS, "data": "café".encode("utf-8")},
        ])

        self.assertEqual(rows[1][CSV_COLUMNS.index("message")], "café ✓ дом")
        self.assertEqual(rows[2][CSV_COLUMNS.index("text")], "café")
        self.assertEqual(rows[2][CSV_COLUMNS.index("data")], "63 61 66 C3 A9")

    def test_export_does_not_mutate_the_exported_events(self):
        events = [{"type": "data", "dir": "rx", "ts": TS, "data": b"AT"}]
        before = [dict(ev) for ev in events]

        events_to_csv_rows(events)

        self.assertEqual(events, before)


class MonitorZoomTests(unittest.TestCase):
    def test_clamp_keeps_sizes_inside_the_supported_range(self):
        self.assertEqual(clamp_font_point_size(MIN_FONT_POINT_SIZE - 5), MIN_FONT_POINT_SIZE)
        self.assertEqual(clamp_font_point_size(MAX_FONT_POINT_SIZE + 5), MAX_FONT_POINT_SIZE)
        self.assertEqual(clamp_font_point_size(14), 14)

    def test_clamp_falls_back_to_the_default_for_unusable_values(self):
        for value in (None, "big", object()):
            with self.subTest(value=value):
                self.assertEqual(clamp_font_point_size(value), DEFAULT_FONT_POINT_SIZE)


if __name__ == "__main__":
    unittest.main()
