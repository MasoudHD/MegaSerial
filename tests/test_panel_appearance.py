import unittest
from copy import deepcopy
from MegaSerial.panel_appearance import normalize_appearance, panel_options
from MegaSerial.panel_model import PanelWorkspace
from MegaSerial.monitor import render_html
from test_monitor import OPTS, TS


class PanelAppearanceTests(unittest.TestCase):
    def test_validation_and_nonmutating_overrides(self):
        opts = deepcopy(OPTS)
        appearance = normalize_appearance({'text': '#abcdef', 'rx': '#102030', 'tx': '#405060',
                                          'show_ts': False, 'show_linenum': False,
                                          'background': 'red; invalid', 'title': 23,
                                          'show_counter': 'false'})
        self.assertNotIn('background', appearance)
        self.assertNotIn('title', appearance)
        self.assertNotIn('show_counter', appearance)
        ev = {'type': 'data', 'dir': 'rx', 'ts': TS, 'data': b'hello'}
        result = render_html(ev, 'ASCII', 16, panel_options(opts, appearance), line_num=9)
        self.assertNotIn('03:04:05', result)
        self.assertNotIn('    9', result)
        self.assertIn('#abcdef', result)
        self.assertIn('#102030', result)
        ev['dir'] = 'tx'
        self.assertIn('#405060', render_html(ev, 'ASCII', 16, panel_options(opts, appearance)))
        self.assertEqual(opts, OPTS)
        self.assertTrue(panel_options(opts, {})['show_ts'])
        self.assertTrue(panel_options(opts, {})['show_linenum'])

    def test_counter_and_appearance_roundtrip(self):
        w = PanelWorkspace({'max_columns': 2, 'row_counts': [2]})
        w.set_appearance('12', {'title': '#ABCDEF', 'show_counter': False, 'show_ts': True})
        for event in [{'type': 'data', 'dir': 'rx', 'panel_id': '12'},
                      {'type': 'data', 'dir': 'rx', 'panel_id': 'unknown'},
                      {'type': 'data', 'dir': 'tx', 'panel_id': '12'},
                      {'type': 'log', 'dir': 'rx'}]:
            w.record_received(event)
        self.assertEqual(w.received_counts, {'12': 1, '11': 1})
        restored = PanelWorkspace.restore(w.to_dict())
        self.assertEqual(restored.to_dict(), w.to_dict())
        restored.set_automatic(True)
        restored.record_received({'type': 'data', 'dir': 'rx', 'panel_id': '12'})
        restored.set_automatic(False)
        self.assertEqual(restored.received_counts['12'], 2)
        self.assertEqual(restored.appearance('12')['title'], '#abcdef')
