"""Characterization tests for current payload conversion and rendering behavior."""
from __future__ import annotations

import unittest

from MegaSerial import utils


class PayloadParsingTests(unittest.TestCase):
    def test_ascii_expands_supported_escapes_and_keeps_unknown_escapes(self):
        self.assertEqual(
            utils.parse_ascii(r'A\n\r\t\0\\\"\'\x41\q'),
            b'A\n\r\t\x00\\\"\'A\\q',
        )

    def test_hex_accepts_prefixes_and_common_separators(self):
        self.assertEqual(utils.parse_hex("0x48, 65;\n6c 6C 6F"), b"Hello")

    def test_binary_ignores_separators_between_complete_bytes(self):
        self.assertEqual(utils.parse_binary("01001000 01101001"), b"Hi")

    def test_invalid_payloads_raise_parse_error(self):
        with self.assertRaisesRegex(utils.ParseError, "Invalid \\\\x escape"):
            utils.parse_ascii(r"\xGG")
        with self.assertRaisesRegex(utils.ParseError, "even number"):
            utils.parse_hex("ABC")
        with self.assertRaisesRegex(utils.ParseError, "non-hex"):
            utils.parse_hex("GG")
        with self.assertRaisesRegex(utils.ParseError, "only contain"):
            utils.parse_binary("0102")
        with self.assertRaisesRegex(utils.ParseError, "multiple of 8"):
            utils.parse_binary("0101")

    def test_parse_input_normalizes_known_format_names_and_unknown_to_ascii(self):
        self.assertEqual(utils.parse_input("48", "hex"), b"H")
        self.assertEqual(utils.parse_input("01001000", "BIN"), b"H")
        self.assertEqual(utils.parse_input("plain", "unrecognized"), b"plain")

    def test_line_ending_labels_append_expected_bytes(self):
        payload = utils.parse_input("AT", utils.FORMAT_ASCII)
        self.assertEqual(payload + utils.LINE_ENDINGS["None"], b"AT")
        self.assertEqual(payload + utils.LINE_ENDINGS["LF (\\n)"], b"AT\n")
        self.assertEqual(payload + utils.LINE_ENDINGS["CR (\\r)"], b"AT\r")
        self.assertEqual(payload + utils.LINE_ENDINGS["CRLF (\\r\\n)"], b"AT\r\n")


class PayloadFormattingTests(unittest.TestCase):
    def test_format_output_covers_supported_monitor_formats(self):
        data = b"A\n\x00B"
        self.assertEqual(utils.format_output(data, "ASCII"), "A\n\u00b7B")
        self.assertEqual(utils.format_output(data, "HEX", bytes_per_row=2), "41 0A\n00 42")
        self.assertEqual(
            utils.format_output(data, "Binary", bytes_per_row=2),
            "01000001 00001010\n00000000 01000010",
        )
        self.assertEqual(
            utils.format_output(b"AB", "Hexdump", bytes_per_row=4),
            "00000000  41 42        |AB|",
        )

    def test_ascii_can_render_non_printable_bytes_as_hex(self):
        self.assertEqual(utils.to_ascii(b"A\x01B", show_nonprintable_as_hex=True), r"A\x01B")

    def test_human_preview_uses_escaped_controls_and_truncates(self):
        self.assertEqual(utils.human_preview(b"A\r\nB\t"), r"A\r\nB\t")
        self.assertEqual(utils.human_preview(b"abcdef", limit=3), "abc\u2026")


class PayloadConstructionTests(unittest.TestCase):
    def test_build_payload_matches_all_formats_and_line_endings(self):
        cases = [
            ("AT", "ASCII", b"AT"),
            ("41 54", "HEX", b"AT"),
            ("01000001 01010100", "Binary", b"AT"),
        ]
        endings = {
            "None": b"",
            "LF (\\n)": b"\n",
            "CR (\\r)": b"\r",
            "CRLF (\\r\\n)": b"\r\n",
        }

        for text, fmt, expected in cases:
            for line_ending, suffix in endings.items():
                with self.subTest(fmt=fmt, line_ending=line_ending):
                    self.assertEqual(utils.build_payload(text, fmt, line_ending), expected + suffix)

    def test_build_payload_preserves_unknown_or_missing_line_ending_fallback(self):
        self.assertEqual(utils.build_payload("AT", "ASCII", "Unknown"), b"AT")
        self.assertEqual(utils.build_payload("AT", "ASCII", None), b"AT")

    def test_build_payload_preserves_invalid_input_errors(self):
        with self.assertRaisesRegex(utils.ParseError, "even number"):
            utils.build_payload("A", "HEX", "CRLF (\\r\\n)")


if __name__ == "__main__":
    unittest.main()
