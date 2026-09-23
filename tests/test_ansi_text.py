import unittest
from MegaSerial.ansi_text import ansi_html, plain_ansi
from MegaSerial.panel_protocol import panel_event


class AnsiTests(unittest.TestCase):
    def test_color_reset_unicode_and_safe_html(self):
        value = 'before \x1b[31m<script>سلام\x1b[0m after'
        result = ansi_html(value)
        self.assertTrue(result.startswith('before '))
        self.assertIn('color:#aa0000', result)
        self.assertIn('&lt;script&gt;سلام', result)
        self.assertNotIn('<script>', result)
        self.assertTrue(result.endswith('</span> after'))
        self.assertEqual(plain_ansi(value), 'before <script>سلام after')

    def test_rgb_indexed_and_incomplete_sequences(self):
        self.assertIn('color:#010203', ansi_html('\x1b[38;2;1;2;3mRGB'))
        self.assertIn('background-color:#ff0000', ansi_html('\x1b[48;5;196mBG'))
        self.assertIn('font-weight:bold', ansi_html('\x1b[1mBold'))
        for value in ('\x1b[38;5mtext', '\x1b[38;2;1mtext', '\x1b[' + '9' * 5000 + 'mtext'):
            self.assertIn('text', ansi_html(value))

    def test_projection_keeps_stored_bytes_and_plain_filter_text(self):
        ev = {'type': 'data', 'data': b'raw', 'panel_ansi': True,
              'panel_payload': '\x1b[31mERROR\x1b[0m'}
        projected = panel_event(ev)
        self.assertEqual(projected['data'], b'ERROR')
        self.assertEqual(ev['data'], b'raw')
        self.assertNotIn('_panel_ansi_text', ev)
