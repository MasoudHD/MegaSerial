import unittest
from MegaSerial.panel_protocol import PanelProtocolParser


class ProtocolTests(unittest.TestCase):
    def test_commands(self):
        parser = PanelProtocolParser()
        for line, kind, ident, payload in [
            ("@PANEL:32|Position test\n", "data", "32", "Position test"),
            ("@PANEL:gps|Fix\n", "data", "gps", "Fix"),
            ("@PANEL:sensor7|\r\n", "data", "sensor7", ""),
            ("@PANEL:موقع|سلام|✓\n", "data", "موقع", "سلام|✓"),
            ("@PANEL_TITLE:gps|گیرنده GPS\n", "title", "gps", "گیرنده GPS"),
        ]:
            with self.subTest(line=line):
                result = parser.parse(line.encode())
                self.assertEqual((result.kind, result.panel_id, result.text), (kind, ident, payload))

    def test_ordinary_malformed_partial_and_binary(self):
        for line in [b"hello\n", b"@PANEL:gps|partial", b"@PANEL:|bad\n",
                     b"@PANEL:gps\n", b"@PANEL:a b|bad\n", b"@PANEL:gps|\xff\n",
                     b"@PANEL:gps|\x00\n", b"@PANEL:gps|a\nb\n"]:
            with self.subTest(line=line):
                self.assertEqual(PanelProtocolParser().parse(line).kind, "normal")
