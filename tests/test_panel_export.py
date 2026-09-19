import csv
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from MegaSerial.monitor import CSV_COLUMNS, CSV_ENCODING, write_events_csv, events_to_csv_rows


class PanelExportTests(unittest.TestCase):
    def test_panel_csv_roundtrip(self):
        message = 'سلام, "GPS"\nnext line'
        events = [
            {'type': 'data', 'dir': 'rx', 'ts': datetime(2026, 1, 1),
             'data': b'raw', 'panel_payload': message, 'panel_id': 'gps'},
            {'type': 'data', 'dir': 'tx', 'data': b'AT'},
            {'type': 'log', 'msg': message},
            {'type': 'data', 'dir': 'rx', 'data': b'unknown', 'panel_id': 'sensor7'},
        ]
        before = deepcopy(events)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'panels.csv'
            self.assertEqual(write_events_csv(path, events, {'gps': 'گیرنده, "GPS"\nTitle'}), 4)
            with path.open(encoding=CSV_ENCODING, newline='') as fh:
                rows = list(csv.DictReader(fh))
        self.assertEqual(rows[0]['panel_id'], 'gps')
        self.assertEqual(rows[0]['panel_title'], 'گیرنده, "GPS"\nTitle')
        self.assertEqual(rows[0]['text'], message.replace('\n', '\\n'))
        self.assertEqual(rows[0]['data'], '72 61 77')
        self.assertEqual(rows[1]['panel_id'], 'general')
        self.assertEqual(rows[1]['panel_title'], 'General')
        self.assertEqual(rows[1]['direction'], 'tx')
        self.assertEqual(rows[2]['message'], message)
        self.assertEqual(rows[3]['panel_id'], 'sensor7')
        self.assertEqual(events, before)
        self.assertEqual(events_to_csv_rows(events)[0], CSV_COLUMNS)
